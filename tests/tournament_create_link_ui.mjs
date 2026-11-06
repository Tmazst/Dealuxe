import assert from 'node:assert/strict';
import vm from 'node:vm';

// Exercise the actual creation entry function, without submitting a tournament.
export async function run(source) {
    const match = source.match(/async function beginCreateTournament\(\) \{[\s\S]*?\n        \}/);
    assert.ok(match, 'Shared create flow exists');
    for (const authenticated of [false,true]) {
        const calls = []; let opened = 0, focused = 0, cleaned = null;
        const window = {location:{href:'https://games.example.test/tournaments?filter=open&create=1#brackets'},
            history:{replaceState:(_state,_title,url) => {cleaned=url;}}};
        const context = vm.createContext({window,URL,
            fetch:async (url,options) => {calls.push([url,options]); return {ok:authenticated};},
            openCreateModal:() => {opened++;},
            document:{getElementById:() => ({focus:() => {focused++;}})}});
        await vm.runInContext(`(${match[0]})()`,context);
        assert.equal(calls.length,1);
        assert.equal(calls[0][0],'/api/auth/me');
        if (!authenticated) {
            assert.equal(window.location.href,'/login?next=%2Ftournaments%3Fcreate%3D1');
            assert.equal(opened,0,'Guests authenticate before seeing the creation form');
        } else {
            assert.equal(opened,1);
            assert.equal(focused,1);
            assert.equal(cleaned,'/tournaments?filter=open#brackets');
        }
    }
    return {passed:true,checks:10};
}
