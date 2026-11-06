"""Spectator privacy and live transport regression tests (isolated test DB)."""
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from app import app, socketio, manager
from database import db, User, Player, Tournament, TournamentBracket, TournamentMatch, GameRoom
from game.models import Card
from controllers.multiplayer_controller import handle_game_over, _auto_play_expired_room
from services.spectator_service import (
    _cache, get_public_snapshot, publish_spectator_update, player_action_result,
)


class SpectatorGamesTest(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context(); self.ctx.push()
        self.old_testing = app.config.get('TESTING')
        app.config['TESTING'] = True
        db.drop_all(); db.create_all(); _cache.clear()
        self.clients = []
        self.users = [User(username=name, email=f'{name}@example.test', password_hash='unused-test-password') for name in ('Lwazi', 'Sibusiso', 'Visitor')]
        db.session.add_all(self.users); db.session.flush()
        db.session.add_all([Player(user_id=user.id) for user in self.users])
        self.tournament = Tournament(tournament_code='SPEC-TEST', tournament_name='Public tournament', tournament_type='standard', creator_id=self.users[0].id, entry_fee=10, max_players=4, current_player_count=2, status='in_progress')
        db.session.add(self.tournament); db.session.flush()
        self.bracket = TournamentBracket(tournament_id=self.tournament.id, round_number=1, round_name='Final', match_number=1, player1_id=self.users[0].id, player2_id=self.users[1].id, status='in_progress')
        db.session.add(self.bracket); db.session.flush()
        self.match = TournamentMatch(tournament_id=self.tournament.id, bracket_id=self.bracket.id, player1_id=self.users[0].id, player2_id=self.users[1].id, status='in_progress')
        db.session.add(self.match); db.session.flush()
        self.game_id, _ = manager.create_game('local')
        self.engine = manager.get_game(self.game_id)
        self.engine.players[0].hand = [Card('7', '♥', 7), Card('K', '♥', 13), Card('Q', '♥', 12)]
        self.engine.players[1].hand = [Card('2', '♣', 2), Card('3', '♣', 3), Card('J', '♠', 11)]
        self.engine.state.phase = 'ATTACK'; self.engine.state.attacker = 0; self.engine.state.defender = 1
        self.engine.state.attack_card = None
        manager.update_game(self.game_id, self.engine)
        self.room = GameRoom(room_code='WATCH1', player1_id=self.users[0].id, player2_id=self.users[1].id, game_id=self.game_id, status='in_progress', tournament_id=self.tournament.id, match_id=self.match.id, is_tournament_game=True, current_turn_player=self.users[0].id, turn_deadline=datetime.utcnow()+timedelta(seconds=60), player1_connected=True, player2_connected=True)
        db.session.add(self.room); db.session.flush()
        self.match.game_room_id = self.room.id; self.bracket.match_id = self.match.id
        db.session.commit()
        self.guest = app.test_client()

    def tearDown(self):
        for client in self.clients:
            if client.is_connected(): client.disconnect()
        manager.delete_game(self.game_id)
        _cache.clear(); db.session.remove(); db.drop_all()
        app.config['TESTING'] = self.old_testing; self.ctx.pop()

    def client(self, user=None):
        client = app.test_client()
        if user:
            with client.session_transaction() as state: state['user_id'] = user.id
        return client

    def socket(self, user=None):
        client = socketio.test_client(app, flask_test_client=self.client(user))
        self.clients.append(client); client.get_received()
        return client

    def public_packet(self, client):
        return [packet['args'][0] for packet in client.get_received() if packet['name'] == 'spectator_update'][-1]

    def assert_private(self, value):
        text = json.dumps(value, ensure_ascii=False)
        for card in ('K♥', 'Q♥', '2♣', '3♣', 'J♠'):
            self.assertNotIn(card, text)
        self.assertNotIn('"hands"', text)
        self.assertNotIn('"hand"', text)
        self.assertNotIn('defender_drawn_card', text)

    def test_guest_page_and_snapshot_have_only_public_state(self):
        response = self.guest.get('/watch/WATCH1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Both players', response.data)
        response = self.guest.get('/api/watch/WATCH1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        payload = response.get_json(); self.assert_private(payload)
        self.assertEqual([p['hand_count'] for p in payload['players']], [3, 3])

    def test_guests_and_logged_in_outsiders_cannot_read_or_mutate_player_api(self):
        for client in (self.guest, self.client(self.users[2])):
            for suffix in ('state', 'player_details', 'leaderboard'):
                self.assertEqual(client.get(f'/api/game/{self.game_id}/{suffix}').status_code, 403)
            for suffix in ('start', 'attack', 'defend', 'draw', 'rule8/drop', 'rule8/crash'):
                self.assertEqual(client.post(f'/api/game/{self.game_id}/{suffix}', json={}).status_code, 403)
        self.assertEqual(self.client(self.users[0]).post(f'/api/game/{self.game_id}/attack', json={'index':0}).status_code, 409)
        self.assertEqual(manager.get_game(self.game_id).get_state()['phase'], 'ATTACK')

    def test_players_only_receive_their_own_hand_via_http(self):
        for index, user in enumerate(self.users[:2]):
            client = self.client(user)
            payload = client.get(f'/api/game/{self.game_id}/state').get_json()
            self.assertEqual(set(payload['hands']), {str(index)})
            self.assertNotIn('hand', payload['players'][1-index])
            payload = client.get(f'/api/game/{self.game_id}/leaderboard').get_json()
            self.assertNotIn('"hand"', json.dumps(payload))

    def test_private_games_and_cancelled_events_are_not_watchable(self):
        self.room.is_tournament_game = False; db.session.commit()
        self.assertEqual(self.guest.get('/watch/WATCH1').status_code, 404)
        self.assertEqual(self.guest.get('/api/watch/WATCH1').status_code, 404)
        client = self.socket(); self.assertFalse(client.emit('watch_game', {'room_code':'WATCH1'}, callback=True)['ok'])
        self.room.is_tournament_game = True; self.tournament.status = 'cancelled'; db.session.commit()
        self.assertEqual(self.guest.get('/api/watch/WATCH1').status_code, 404)

    def test_live_attack_is_public_and_socket_results_do_not_reveal_hands(self):
        viewer = self.socket(); viewer.emit('watch_game', {'room_code':'WATCH1'})
        initial = self.public_packet(viewer)
        actor = self.socket(self.users[0])
        actor.emit('game_action', {'room_code':'WATCH1', 'action':'attack', 'data':{'index':0}})
        payload = self.public_packet(viewer); self.assert_private(payload)
        self.assertEqual(payload['attack_card'], '7♥')
        self.assertEqual(payload['players'][0]['hand_count'], 2)
        self.assertGreater(payload['version'], initial['version'])
        self.assertIn('attacked with 7♥', payload['events'][-1]['text'])
        packets = actor.get_received()
        self.assertNotIn('2♣', json.dumps(packets, ensure_ascii=False))
        self.assertNotIn('3♣', json.dumps(packets, ensure_ascii=False))
        viewer.emit('leave_watch_game')
        publish_spectator_update(socketio, self.room, self.engine.get_state(), action='resumed')
        self.assertFalse(any(p['name']=='spectator_update' for p in viewer.get_received()))

    def test_spectators_cannot_play_pause_resume_or_reconnect_as_players(self):
        for user in (None, self.users[2]):
            viewer = self.socket(user); viewer.emit('watch_game', {'room_code':'WATCH1'}); viewer.get_received()
            for event, data in (
                ('game_action', {'action':'attack','data':{'index':0}}),
                ('request_pause', {}), ('approve_pause', {'approved':True}),
                ('resume_game', {}), ('reconnect_to_room', {}),
            ):
                viewer.emit(event, dict(room_code='WATCH1', **data))
            self.assertEqual(manager.get_game(self.game_id).get_state()['phase'], 'ATTACK')
            db.session.refresh(self.room); self.assertEqual(self.room.status, 'in_progress')

    def test_watch_disconnect_does_not_mark_player_offline(self):
        viewer = self.socket(self.users[0]); viewer.emit('watch_game', {'room_code':'WATCH1'}); viewer.disconnect()
        db.session.refresh(self.room); self.assertTrue(self.room.player1_connected)

    def test_pause_resume_and_resubscribe_send_fresh_public_snapshots(self):
        viewer = self.socket(); viewer.emit('watch_game', {'room_code':'WATCH1'}); viewer.get_received()
        player = self.socket(self.users[1]); player.emit('approve_pause', {'room_code':'WATCH1','approved':True})
        self.assertEqual(self.public_packet(viewer)['status'], 'paused')
        player.emit('resume_game', {'room_code':'WATCH1'})
        self.assertEqual(self.public_packet(viewer)['status'], 'in_progress')
        viewer.emit('watch_game', {'room_code':'WATCH1'})
        self.assert_private(self.public_packet(viewer))

    def test_finished_match_never_reveals_hands_and_survives_engine_expiry(self):
        viewer = self.socket(); viewer.emit('watch_game', {'room_code':'WATCH1'}); viewer.get_received()
        state = self.engine.get_state(); state['winner'] = 0; state['game_over'] = True
        with patch('controllers.tournament_controller.record_tournament_match_result', return_value=(None,None)):
            handle_game_over(self.room, state, socketio)
        payload = self.public_packet(viewer); self.assert_private(payload)
        self.assertEqual(payload['status'], 'completed'); self.assertEqual(payload['winner_index'], 0)
        manager.delete_game(self.game_id)
        payload = self.guest.get('/api/watch/WATCH1').get_json()
        self.assertEqual(payload['status'], 'completed'); self.assert_private(payload)

    def test_expired_engine_is_reported_without_fabricating_hands(self):
        manager.delete_game(self.game_id)
        payload = self.guest.get('/api/watch/WATCH1').get_json()
        self.assertFalse(payload['available'])
        self.assertEqual([p['hand_count'] for p in payload['players']], [None,None])

    def test_failed_defense_and_draw_results_cannot_leak_private_cards(self):
        failed = {'error':'Wrong sum','cards_played':['2♣','3♣'],'hands':{0:['K♥'],1:['J♠']}}
        self.assertEqual(player_action_result(failed, False), None)
        self.assertEqual(player_action_result(failed, True), {'error':'Wrong sum'})
        wrapped = {'results':{'ok':True}, 'ui_state':{'hands':{0:['K♥'],1:['J♠']}}}
        self.assertEqual(player_action_result(wrapped, True), {'ok':True})

    def test_automatic_moves_reach_spectators(self):
        viewer = self.socket(); viewer.emit('watch_game', {'room_code':'WATCH1'}); viewer.get_received()
        self.room.turn_deadline = datetime.utcnow()-timedelta(seconds=120); db.session.commit()
        _auto_play_expired_room(socketio, manager, self.room, datetime.utcnow())
        payload = self.public_packet(viewer); self.assert_private(payload)
        self.assertEqual(payload['attack_card'], '7♥')

    def test_live_match_metadata_has_watch_links(self):
        payload = self.guest.get(f'/api/tournaments/{self.tournament.id}/overview').get_json()
        self.assertEqual(payload['matches'][0]['watch_url'], '/watch/WATCH1')
        html = self.guest.get(f'/spectators/tournaments/{self.tournament.id}').get_data(as_text=True)
        self.assertIn('live-fixtures', html)

    def test_drawn_card_is_private_and_public_history_is_bounded(self):
        viewer = self.socket(); viewer.emit('watch_game', {'room_code':'WATCH1'}); viewer.get_received()
        attacker = self.socket(self.users[0])
        attacker.emit('game_action', {'room_code':'WATCH1','action':'attack','data':{'index':0}})
        viewer.get_received(); attacker.get_received()
        engine = manager.get_game(self.game_id)
        engine.deck.cards.append(Card('A', '♦', 1)); manager.update_game(self.game_id, engine)
        defender = self.socket(self.users[1])
        defender.emit('game_action', {'room_code':'WATCH1','action':'draw','data':{}})
        payload = self.public_packet(viewer); self.assert_private(payload)
        self.assertNotIn('A♦', json.dumps(payload, ensure_ascii=False))
        self.assertNotIn('A♦', json.dumps(attacker.get_received(), ensure_ascii=False))
        self.assertEqual(payload['players'][1]['hand_count'], 4)
        for _ in range(14): publish_spectator_update(socketio, self.room, action='resumed')
        self.assertEqual(len(get_public_snapshot(self.room, manager)['events']), 12)

    def test_failed_defense_does_not_publish_unplayed_cards(self):
        viewer = self.socket(); viewer.emit('watch_game', {'room_code':'WATCH1'}); viewer.get_received()
        attacker = self.socket(self.users[0])
        attacker.emit('game_action', {'room_code':'WATCH1','action':'attack','data':{'index':0}})
        viewer.get_received(); attacker.get_received()
        defender = self.socket(self.users[1])
        defender.emit('game_action', {'room_code':'WATCH1','action':'defend','data':{'card_indices':[0,1]}})
        self.assertFalse(any(p['name']=='spectator_update' for p in viewer.get_received()))
        text = json.dumps(attacker.get_received(), ensure_ascii=False)
        self.assertNotIn('2♣', text); self.assertNotIn('3♣', text)

    def test_spectator_storage_outage_does_not_interrupt_player_move(self):
        actor = self.socket(self.users[0])
        with patch('services.spectator_service._save', side_effect=RuntimeError('test outage')):
            actor.emit('game_action', {'room_code':'WATCH1','action':'attack','data':{'index':0}})
        self.assertEqual(manager.get_game(self.game_id).get_state()['attack_card'], '7♥')
        self.assertTrue(any(p['name']=='game_update' for p in actor.get_received()))

    def prepare_eight_exchange(self):
        engine = manager.get_game(self.game_id)
        engine.players[0].hand[0] = Card('8', '♥', 8)
        engine.players[1].hand[1] = Card('6', '♦', 6)
        manager.update_game(self.game_id, engine)
        viewer = self.socket(); viewer.emit('watch_game', {'room_code':'WATCH1'}); viewer.get_received()
        attacker = self.socket(self.users[0]); defender = self.socket(self.users[1])
        attacker.emit('game_action', {'room_code':'WATCH1','action':'attack','data':{'index':0}})
        attack = self.public_packet(viewer)
        return viewer, attacker, defender, attack

    def test_eight_attack_and_two_six_defense_stay_together_until_next_attack(self):
        viewer, attacker, defender, attack = self.prepare_eight_exchange()
        self.assertEqual(attack['exchange']['attack_card'], '8♥')
        self.assertEqual(attack['exchange']['outcome'], 'pending')
        defender.emit('game_action', {'room_code':'WATCH1','action':'defend','data':{'card_indices':[0,1]}})
        defended = self.public_packet(viewer)
        exchange = defended['exchange']
        self.assertEqual(exchange['attack_card'], '8♥')
        self.assertEqual(exchange['defense_cards'], ['2♣','6♦'])
        self.assertEqual(exchange['target_value'], 8)
        self.assertEqual(exchange['id'], attack['exchange']['id'])
        self.assertEqual((exchange['attacker_index'], exchange['defender_index']), (0,1))
        self.assertEqual(exchange['outcome'], 'defended')
        self.assertIn('2 + 6 = 8', defended['events'][-1]['text'])
        reconnected = self.guest.get('/api/watch/WATCH1').get_json()
        self.assertEqual(reconnected['exchange'], exchange)
        for private in ('K♥','Q♥','J♠','"hands"','"hand"'):
            self.assertNotIn(private, json.dumps(reconnected, ensure_ascii=False))
        defender.emit('game_action', {'room_code':'WATCH1','action':'attack','data':{'index':0}})
        next_attack = self.public_packet(viewer)
        self.assertEqual(next_attack['exchange']['attack_card'], 'J♠')
        self.assertEqual(next_attack['exchange']['defense_cards'], [])
        self.assertNotEqual(next_attack['exchange']['id'], exchange['id'])
        self.assertTrue(any('2 + 6 = 8' in event['text'] for event in next_attack['events']))

    def test_first_update_can_reconstruct_defense_in_an_already_running_match(self):
        engine = manager.get_game(self.game_id)
        engine.players[0].hand[0] = Card('8', '♥', 8)
        engine.players[1].hand[1] = Card('6', '♦', 6)
        engine.attack(0, 0); manager.update_game(self.game_id, engine)
        _cache.clear()
        defender = self.socket(self.users[1])
        defender.emit('game_action', {'room_code':'WATCH1','action':'defend','data':{'card_indices':[0,1]}})
        payload = self.guest.get('/api/watch/WATCH1').get_json()
        self.assertEqual(payload['exchange']['attack_card'], '8♥')
        self.assertEqual(payload['exchange']['defense_cards'], ['2♣','6♦'])

    def test_draw_keeps_attack_visible_without_exposing_drawn_card(self):
        viewer, attacker, defender, attack = self.prepare_eight_exchange()
        engine = manager.get_game(self.game_id)
        engine.deck.cards.append(Card('A','♦',1)); manager.update_game(self.game_id, engine)
        defender.emit('game_action', {'room_code':'WATCH1','action':'draw','data':{}})
        payload = self.public_packet(viewer)
        self.assertEqual(payload['exchange']['attack_card'], '8♥')
        self.assertEqual(payload['exchange']['outcome'], 'drew')
        self.assertEqual(payload['exchange']['defense_cards'], [])
        self.assertNotIn('A♦', json.dumps(payload, ensure_ascii=False))
        self.assertIn('drew a hidden card', payload['events'][-1]['text'])

    def test_winning_defense_retains_the_complete_public_exchange(self):
        viewer, attacker, defender, attack = self.prepare_eight_exchange()
        engine = manager.get_game(self.game_id)
        engine.players[1].hand[2] = Card('A','♠',1); manager.update_game(self.game_id, engine)
        with patch('controllers.tournament_controller.record_tournament_match_result', return_value=(None,None)):
            defender.emit('game_action', {'room_code':'WATCH1','action':'defend','data':{'card_indices':[0,1]}})
        payload = self.public_packet(viewer)
        self.assertEqual(payload['status'], 'completed')
        self.assertEqual(payload['exchange']['outcome'], 'defended')
        self.assertEqual(payload['exchange']['defense_cards'], ['2♣','6♦'])
        self.assertEqual(payload['exchange']['attack_card'], '8♥')
        self.assertNotIn('A♠', json.dumps(payload, ensure_ascii=False))

    def test_defense_uses_actual_attack_if_previous_broadcast_was_missed(self):
        from services.spectator_service import _update_exchange, _exchange_event
        payload = {'version':2, 'players':[{'name':'Lwazi'},{'name':'Sibusiso'}],
                   'exchange':{'attack_card':'7♥','outcome':'pending'}}
        before = {'attack_card':'8♥','attack_card_value':8,'attacker':0,'defender':1}
        _update_exchange(payload, 'defend', 1, ['2♣','6♦'], before, None)
        self.assertEqual(payload['exchange']['attack_card'], '8♥')
        self.assertIn('2 + 6 = 8', _exchange_event(payload, 'defend', 1, ''))
        before = {'attack_card':'J♥','attack_card_value':11,'attacker':0,'defender':1}
        _update_exchange(payload, 'defend', 1, ['A♣','10♦'], before, None)
        self.assertIn('1 + 10 = 11', _exchange_event(payload, 'defend', 1, ''))
