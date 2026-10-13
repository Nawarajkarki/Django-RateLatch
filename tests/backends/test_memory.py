from django_ratelatch.backends.memory import MemoryBackend



def test_get_returns_none_for_unknown_key():
    backend = MemoryBackend()
    result =  backend.get("unknown_key")
    assert result is None
    


def test_set_key_and_get_key():
    
    key = "user123"
    state = {"window_id" : 1215, "request_count" : 10}
    
    backend = MemoryBackend()
    
    success = backend.set(key, state)
    
    # Retrieve and verify the value
    resp_state = backend.get(key)
    assert resp_state is not None
    assert resp_state == state
    assert resp_state["window_id"] == 1215
    
    

def test_overwrite_existing_key():
    key = "user444"
    state1 = {"window_id" : 1215, "request_count" : 10}
    state2 = {"window_id" : 1233, "request_count" : 1}
    
    backend = MemoryBackend()
    backend.set(key, state1)
    backend.set(key, state2)
    
    response = backend.get(key)
    assert response is not None
    assert response == state2
    assert response["window_id"] == state2["window_id"]
    assert response["request_count"] == state2["request_count"]




def test_multiple_independent_keys():
    
    backend = MemoryBackend()
    
    backend.set("keya", "valuea")
    backend.set("keyb", "valueb")
    
    assert backend.get("keya") == "valuea"
    assert backend.get("keyb") == "valueb"



def test_get_returns_none_after_timeout(monkeypatch):
    current_time = [100.0]

    monkeypatch.setattr(
        "django_ratelatch.backends.memory.monotonic",
        lambda: current_time[0],
    )

    backend = MemoryBackend()
    state = {"window_id": 1, "request_count": 1}

    backend.set("client-1", state, timeout=5)

    assert backend.get("client-1") == state

    current_time[0] = 104.9
    assert backend.get("client-1") == state

    current_time[0] = 105.0
    assert backend.get("client-1") is None