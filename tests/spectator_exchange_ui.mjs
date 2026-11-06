// Exported run(source) checks the actual spectator client with a small DOM adapter.
// Use a current Node.js release; no browser libraries or dependencies are required.
import assert from 'node:assert/strict';
import vm from 'node:vm';

class Element {
    constructor() {
        this.children = []; this.dataset = {}; this.attributes = {}; this.classes = new Set();
        this.style = {setProperty() {}}; this._text = '';
        this.classList = {add: (...names) => names.forEach(name => this.classes.add(name)),
            remove: (...names) => names.forEach(name => this.classes.delete(name)),
            toggle: (name, enabled) => enabled ? this.classes.add(name) : this.classes.delete(name),
            contains: name => this.classes.has(name)};
    }
    set className(value) { this.classes = new Set(value.split(' ').filter(Boolean)); }
    get className() { return [...this.classes].join(' '); }
    set textContent(value) { this._text = value; this.children = []; }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this._text = ''; this.children = children; }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener() {}
    cloneNode() { const node = new Element(); node.textContent = this._text; return node; }
    querySelector(selector) { return this.parts[selector]; }
}

export function run(source) {
const ids = {};
for (const id of ['spectator-game','connection-status','watch-notice','tournament-name','match-title','match-round',
    'public-cards','exchange-defense','defense-cards','exchange-outcome','exchange-explanation','pile-label',
    'defense-label','turn-status','turn-timer','public-moves','match-completed','finished-title','player-0','player-1','hand-0','hand-1']) ids[id] = new Element();
for (const index of [0,1]) ids[`player-${index}`].parts = Object.fromEntries(
    ['.player-name','.avatar','.card-count'].map(key => [key,new Element()]));
ids['spectator-game'].dataset = {roomCode:'DEMO',transports:'["polling"]'};
const events = {};
const motion = {matches:false};
const document = {hidden:false, getElementById:id => ids[id], createElement:() => new Element(), addEventListener() {}};
const socket = {on:(event,fn) => {events[event] = fn;}, emit() {}, disconnect() {}, connect() {}};
const context = vm.createContext({document, window:{matchMedia:() => motion, addEventListener() {}},
    io:() => socket, fetch:() => new Promise(() => {}), setInterval:() => 1, clearInterval() {}, console});
vm.runInContext(source,context);
let version = 0;
const snapshot = exchange => ({room_code:'DEMO', version:++version, players:[{name:'Lwazi',hand_count:5},{name:'Sibusiso',hand_count:5}],
    tournament_name:'Demo',round_name:'Final',match_number:1,status:'in_progress',available:true,
    attacker:0,defender:1,phase:'DEFENSE',events:[],exchange});
const attack = id => ({id,kind:'attack',attack_card:'8♥',target_value:8,attacker_index:0,defender_index:1,defense_cards:[],outcome:'pending'});
events.connect(); events.spectator_update(snapshot(null));
events.spectator_update(snapshot(attack(1)));
const eight = ids['public-cards'].children[0];
assert.ok(eight.classList.contains('card-enter-attack'), 'New live attack animates');
events.spectator_update(snapshot(attack(1)));
assert.strictEqual(ids['public-cards'].children[0], eight, 'Duplicate snapshots preserve the card DOM');
const defended = {...attack(1),defense_cards:['2♣','6♦'],outcome:'defended'};
events.spectator_update(snapshot(defended));
assert.strictEqual(ids['public-cards'].children[0], eight, 'Defense keeps the original attack on the table');
assert.equal(ids['defense-cards'].children.length,2);
assert.ok(ids['defense-cards'].children.every(card => card.classList.contains('card-enter-defense')));
assert.equal(ids['exchange-outcome'].textContent,'Successful defense: 2 + 6 = 8');
const two = ids['defense-cards'].children[0];
events.spectator_update(snapshot(defended));
assert.strictEqual(ids['defense-cards'].children[0],two, 'Refresh does not replay defense animations');
events.spectator_update(snapshot(attack(2)));
assert.notStrictEqual(ids['public-cards'].children[0],eight, 'A new attack starts a fresh exchange');
assert.equal(ids['defense-cards'].children[0].textContent,'Waiting for the defense');
events.spectator_update(snapshot({...attack(2),outcome:'drew'}));
assert.ok(ids['exchange-outcome'].textContent.includes('drew a card'));
assert.equal(ids['defense-cards'].children[0].attributes['aria-label'],'A hidden card was drawn');
assert.ok(ids['public-cards'].textContent.includes('8♥'));
motion.matches = true;
events.spectator_update(snapshot(attack(3)));
assert.ok(!ids['public-cards'].children[0].classList.contains('card-enter-attack'), 'Reduced motion disables movement');
motion.matches = false;
events.connect(); events.spectator_update(snapshot(attack(4)));
assert.ok(!ids['public-cards'].children[0].classList.contains('card-enter-attack'), 'Reconnect does not replay old moves');
document.hidden = true;
events.spectator_update(snapshot(attack(5)));
assert.ok(!ids['public-cards'].children[0].classList.contains('card-enter-attack'), 'Hidden tabs do not animate');
document.hidden = false;
const trail = {id:6,kind:'trail',attacker_index:0,defender_index:1,trail_cards:['2♣'],outcome:'trailing'};
events.spectator_update(snapshot(trail));
const firstTrail = ids['public-cards'].children[0];
events.spectator_update(snapshot({...trail,trail_cards:['2♣','3♦']}));
assert.strictEqual(ids['public-cards'].children[0],firstTrail,'Trail updates animate only the newly added card');
assert.equal(ids['public-cards'].children.length,2);
const face = {...attack(7),attack_card:'J♣',target_value:11,defense_cards:['A♠','10♦'],outcome:'defended'};
events.spectator_update(snapshot(face));
assert.equal(ids['exchange-outcome'].textContent,'Successful defense: 1 + 10 = 11');
const lastCard = ids['public-cards'].children[0];
events.spectator_update({...snapshot(attack(8)),version:1});
assert.strictEqual(ids['public-cards'].children[0],lastCard,'Stale packets cannot replace the current exchange');
events.spectator_update(snapshot({...face,id:9,attacker_index:1,defender_index:0}));
assert.ok(ids['public-cards'].children[0].classList.contains('card-enter-defense'), 'Bottom player attacks from below');
assert.ok(ids['defense-cards'].children[0].classList.contains('card-enter-attack'), 'Top player defends from above');
assert.equal(ids['match-completed'].hidden,true,'Finished actions remain hidden during play');
events.spectator_update({...snapshot(defended),status:'completed',winner_index:1});
assert.equal(ids['match-completed'].hidden,false,'Finished actions appear after completion');
assert.equal(ids['finished-title'].textContent,'Sibusiso takes the win!');
assert.ok(ids['public-cards'].textContent.includes('8♥'),'The final exchange stays visible alongside the actions');
events.spectator_update({...snapshot(null),status:'completed',winner_index:null});
assert.equal(ids['public-cards'].textContent,'No public moves were recorded for this match');
events.spectator_update(snapshot(attack(10)));
assert.equal(ids['match-completed'].hidden,true,'Live snapshots hide completed-match actions');
return {passed:true,checks:27};
}
