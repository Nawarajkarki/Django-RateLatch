import pytest

from django_ratelatch.backends.memory import MemoryBackend
from django_ratelatch.core.algorithms.fixed_window import FixedWindow




def test_rejects_on_neg_limit():
    with pytest.raises(ValueError):
        FixedWindow(limit = -1, window_size=120, backend=MemoryBackend())
        

def test_rejects_on_neg_window_size():
    with pytest.raises(ValueError):
        FixedWindow(limit=10, window_size=-1, backend=MemoryBackend())
        
        
def test_rejects_on_zero_limit():
    with pytest.raises(ValueError):
        FixedWindow(limit = 0, window_size=120, backend=MemoryBackend())
        

def test_rejects_on_zero_window_size():
    with pytest.raises(ValueError):
        FixedWindow(limit=10, window_size=0, backend=MemoryBackend())
        

def test_rejects_when_request_limit_exceeds(monkeypatch):
    backend = MemoryBackend()
    limiter = FixedWindow(
        limit = 2, 
        window_size=10, 
        backend=backend
    )
    key = "user123"
    
    monkeypatch.setattr(
        "django_ratelatch.core.algorithms.fixed_window.time",
        lambda : 1000
    )
    
    # requst 1 --> Should Accept
    resp = limiter.check(key)
    assert resp["allowed"] == True
    
    # requst 2 --> Should Accept
    resp = limiter.check(key)
    assert resp["allowed"] == True
    
    # requst 3 --> Should reject
    resp = limiter.check(key)
    assert resp["allowed"] == False
    
    resp = backend.get("fixed_window:user123")
    assert resp is not None
    assert resp['request_count'] == 2

    
    
def test_allows_requset_after_window_reset(monkeypatch):
    backend = MemoryBackend()
    
    limiter = FixedWindow(
        limit = 2,
        window_size = 60,
        backend = backend
    )
    
    monkeypatch.setattr(
        "django_ratelatch.core.algorithms.fixed_window.time",
        lambda : 1000
    )
    
    assert limiter.check('user1')['allowed'] is True
    assert limiter.check('user1')['allowed'] is True
    assert limiter.check('user1')['allowed'] is False
    
    memory_resp = backend.get('fixed_window:user1')
    assert memory_resp is not None
    prev_window_id = memory_resp['window_id']
    
    monkeypatch.setattr(
        "django_ratelatch.core.algorithms.fixed_window.time",
        lambda : 1060
    )
    
    assert limiter.check('user1')['allowed'] is True
    memory_resp = backend.get('fixed_window:user1')
    assert memory_resp is not None
    assert memory_resp['window_id'] != prev_window_id
    assert memory_resp['request_count'] == 1


def test_multiple_keys(monkeypatch):
    backend = MemoryBackend()
    
    limiter = FixedWindow(
        limit = 3,
        window_size = 60,
        backend = backend
    )
    
    monkeypatch.setattr(
        "django_ratelatch.core.algorithms.fixed_window.time",
        lambda : 1000    
    )
    
    assert limiter.check("user1")['allowed'] is True
    assert limiter.check("user1")['allowed'] is True
    assert limiter.check("user2")['allowed'] is True
    assert limiter.check("user2")['allowed'] is True
    
    assert limiter.check('user1')["allowed"] is True
    assert limiter.check('user2')["allowed"] is True
    
    
    assert limiter.check('user1')['allowed'] is False
    assert limiter.check('user2')['allowed'] is False
    
    
    assert limiter.check('user3')['allowed'] is True
    assert limiter.check('user3')['allowed'] is True
    assert limiter.check('user3')['allowed'] is True
    assert limiter.check('user3')['allowed'] is False
    
    
    monkeypatch.setattr(
            "django_ratelatch.core.algorithms.fixed_window.time",
            lambda : 1060    
        )
    
    assert limiter.check('user1')['allowed'] is True
    state1 = backend.get('fixed_window:user1')
    assert state1 is not None
    assert state1['request_count'] == 1
    
    assert limiter.check('user2')['allowed'] is True
    state2 = backend.get('fixed_window:user2')
    assert state2 is not None
    assert state2['request_count'] == 1
    
    
    assert limiter.check('user3')['allowed'] is True
    state3 = backend.get('fixed_window:user3')
    assert state3 is not None
    assert state3['request_count'] == 1
    
    
    
    
def test_rejected_response_includes_retry_after(monkeypatch):
    monkeypatch.setattr(
        "django_ratelatch.core.algorithms.fixed_window.time",
        lambda: 1000,
    )

    limiter = FixedWindow(limit=1, window_size=60, backend=MemoryBackend())

    assert limiter.check("client-1") == {"allowed": True}
    assert limiter.check("client-1") == {
        "allowed": False,
        "retry_after": 20,
    }


def test_retry_after_rounds_up_to_whole_seconds(monkeypatch):
    monkeypatch.setattr(
        "django_ratelatch.core.algorithms.fixed_window.time",
        lambda: 1005.2,
    )

    limiter = FixedWindow(limit=1, window_size=60, backend=MemoryBackend())

    limiter.check("client-1")
    result = limiter.check("client-1")

    assert result["retry_after"] == 15


@pytest.mark.parametrize("value", [True, False])
def test_rejects_boolean_limit(value):
    with pytest.raises(TypeError):
        FixedWindow(limit=value, window_size=60, backend=MemoryBackend())



def test_state_expires_when_fixed_window_ends(monkeypatch):
    wall_clock = [1005.0]
    monotonic_clock = [50.0]

    monkeypatch.setattr(
        "django_ratelatch.core.algorithms.fixed_window.time",
        lambda: wall_clock[0],
    )
    monkeypatch.setattr(
        "django_ratelatch.backends.memory.monotonic",
        lambda: monotonic_clock[0],
    )

    backend = MemoryBackend()
    limiter = FixedWindow(limit=2, window_size=60, backend=backend)

    assert limiter.check("client-1") == {"allowed": True}
    assert backend.get("fixed_window:client-1") is not None

    # At wall-clock 1005, this window ends at 1020: 15 seconds remain.
    monotonic_clock[0] = 64.9
    assert backend.get("fixed_window:client-1") is not None

    wall_clock[0] = 1020.0
    monotonic_clock[0] = 65.0
    assert backend.get("fixed_window:client-1") is None