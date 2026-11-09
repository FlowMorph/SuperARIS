"""Orca ownership and draft-safe delivery use native-shaped observations."""
from copy import deepcopy

import pytest

from superaris import delivery, receiver
from superaris.orca import Orca, OrcaError
from superaris.state import directory, write


@pytest.fixture
def observed(tmp_path, monkeypatch):
    binary = tmp_path / 'orca'
    binary.touch()
    client = Orca(tmp_path, str(binary), {'host': 'orca', 'session': 'test'})
    terminal = {'handle': 'term-original', 'incarnationId': 'pty-original', 'ptyId': 'pty-id',
                'tabId': 'tab', 'leafId': 'leaf', 'worktreeId': 'workspace',
                'worktreePath': str(tmp_path), 'agentIdentity': 'codex', 'executionHostId': 'local',
                'connected': True, 'writable': True, 'orphaned': False}
    workspace = {'worktreeId': 'workspace', 'hostId': 'local', 'path': str(tmp_path),
                 'agents': [{'paneKey': 'tab:leaf', 'agentType': 'codex', 'hasLivePty': True, 'state': 'done'}]}
    monkeypatch.setattr(client, 'ensure_ready', lambda: {'runtime': {'runtimeId': 'runtime-original',
                        'capabilities': ['terminal.prompt-delivery.v1']}})
    monkeypatch.setattr(client, 'terminal', lambda handle: deepcopy(terminal))
    monkeypatch.setattr(client, '_workspace', lambda **kw: deepcopy(workspace))
    role = client.verify_owner({'pane_id': 'term-original', 'harness': 'codex', 'automation_owned': True}, tmp_path)
    write(directory(tmp_path) / 'launch.json', {'host': 'orca', 'session': 'test', 'roles': {'main': role}})
    return tmp_path, client, role, terminal, workspace


def test_verified_identity_has_no_invented_native_pid(observed):
    project, client, role, _, _ = observed
    assert role['pid'] is None and role['native_session_id'] is None
    assert role['process_incarnation'] == 'pty-original'
    signature = receiver.signature({'host': 'orca', 'session': 'test', 'roles': {'main': role}})
    assert signature['runtime_id'] == 'runtime-original'
    assert receiver.same_owner(signature, {**signature, 'host': 'herdr'}) is False
    assert receiver.same_owner(signature, {**signature, 'execution_environment': 'remote'}) is False


@pytest.mark.parametrize('change', ['incarnation', 'agent', 'execution', 'orphaned', 'exited', 'peer-absent', 'peer-agent'])
def test_changed_original_occupant_is_rejected(observed, change):
    project, client, role, terminal, workspace = observed
    if change == 'incarnation': terminal['incarnationId'] = 'replacement'
    elif change == 'agent': terminal['agentIdentity'] = 'claude'
    elif change == 'execution': terminal['executionHostId'] = 'remote'
    elif change == 'orphaned': terminal['orphaned'] = True
    elif change == 'exited': terminal['exitCause'] = {'kind': 'exit', 'exitCode': 0}
    elif change == 'peer-absent': workspace['agents'] = []
    else: workspace['agents'][0]['agentType'] = 'claude'
    with pytest.raises(OrcaError): client.verify_owner(role, project)


def test_human_draft_revokes_without_send_and_retains_native_notice(observed, monkeypatch):
    project, client, role, _, _ = observed
    calls = []
    monkeypatch.setattr(client, 'read_screen', lambda handle: {'source': 'screen', 'tail': ['› HUMAN DRAFT']})
    monkeypatch.setattr(client, 'send_prompt', lambda *a: calls.append(a))
    monkeypatch.setattr(client, 'notice', lambda title, text: {'notice_file': 'original-notice'})
    result = delivery.deliver(client, project, role, 'scoped work')
    assert result['delivery'] == 'visible_notice' and result['revoke_automation'] is True
    assert result['notice']['notice_file'] == 'original-notice' and calls == []


def test_empty_screen_sends_once_and_preserves_real_receipt(observed, monkeypatch):
    project, client, role, _, _ = observed
    calls = []
    native = {'accepted': True, 'prompt': {'requestId': 'issued-by-orca', 'stages': ['turn_started']}}
    monkeypatch.setattr(client, 'read_screen', lambda handle: {'source': 'screen', 'tail': ['› Ask Codex to do anything']})
    monkeypatch.setattr(client, 'send_prompt', lambda *a: calls.append(a) or native)
    result = delivery.deliver(client, project, role, 'scoped work')
    assert result['delivery'] == 'submitted' and result['acceptance'] == 'not_evaluated'
    assert result['native_receipt'] == native and len(calls) == 1


def test_native_send_never_accepts_unsupported_old_host_placeholder(observed, monkeypatch):
    _, client, _, _, _ = observed
    calls = []
    monkeypatch.setattr(client, 'call', lambda *a, **kw: calls.append(a) or {
        'result': {'send': {'accepted': True, 'prompt': {'requestId': 'unsupported-old-host'}}}})
    with pytest.raises(OrcaError): client.send_prompt('term-original', 'work', request_id='unsupported-old-host')
    assert calls == []
    with pytest.raises(OrcaError): client.send_prompt('term-original', 'work')
    assert len(calls) == 1


def test_new_launch_waits_for_same_pty_peer_without_resending(observed, monkeypatch):
    project, client, role, terminal, workspace = observed
    workspace['agents'] = []
    pauses = []
    def ready(seconds):
        pauses.append(seconds)
        workspace['agents'] = [{'paneKey': 'tab:leaf', 'agentType': 'codex', 'hasLivePty': True, 'state': 'done'}]
    monkeypatch.setattr('time.sleep', ready)
    result = client.wait_owner(role, project)
    assert result['process_incarnation'] == role['process_incarnation'] and pauses == [0.25]
    terminal['incarnationId'] = 'changed'
    with pytest.raises(OrcaError, match='incarnation changed'):
        client.wait_owner(role, project)


def test_new_unverified_launch_pin_survives_timeout_and_rejects_replaced_pty(observed):
    from superaris.state import read
    project, client, _, terminal, workspace = observed
    record = {'pane_id': 'term-original', 'harness': 'codex', 'created': True,
              'delivery': {'phase': 'submitted'}, 'launch_receipt': {'result': {'operationId': 'actual-native-id'}}}
    path = directory(project) / 'launch.json'
    original = {'host': 'orca', 'session': 'test', 'roles': {'main': record}}
    write(path,original)
    workspace['agents'] = []
    with pytest.raises(OrcaError, match='no longer observed'):
        client.wait_owner(record,project,timeout=0,on_observed=lambda:write(path,original))
    restored = read(path)['roles']['main']
    assert restored['process_incarnation'] == 'pty-original'
    assert restored['runtime_id'] == 'runtime-original'
    assert restored['launch_receipt']['result']['operationId'] == 'actual-native-id'
    terminal['incarnationId'] = 'pty-replacement'
    workspace['agents'] = [{'paneKey':'tab:leaf','agentType':'codex','hasLivePty':True,'state':'done'}]
    with pytest.raises(OrcaError,match='incarnation changed'):
        client.verify_owner(restored,project)


@pytest.mark.parametrize('new,code,opens', [(True,'runtime_unavailable',True), (False,'runtime_unavailable',False), (True,'permission_denied',False)])
def test_closed_runtime_native_error_only_opens_confirmed_new_project(observed,monkeypatch,new,code,opens):
    _,client,_,_,_=observed
    calls=[]
    def unavailable():
        raise OrcaError('actual native status error',{'ok':False,'error':{'code':code}})
    monkeypatch.setattr(client,'status',unavailable)
    monkeypatch.setattr(client,'call',lambda *a,**kw:calls.append(a) or {})
    if opens:
        assert client.ensure_startable(new=new)['runtime']['runtimeId']=='runtime-original'
        assert calls==[('open',)]
    else:
        with pytest.raises(OrcaError):client.ensure_startable(new=new)
        assert calls==[]
