from engine.ui import ToastQueue


def test_toast_queue_shows_first_then_advances():
    queue = ToastQueue()
    queue.enqueue("First", seconds=1.0)
    queue.enqueue("Second", seconds=1.0)
    assert queue.current_text == "First"

    queue.update(1.0)
    assert queue.current_text == "Second"

    queue.update(1.0)
    assert queue.current_text == ""


def test_toast_queue_ignores_empty_messages():
    queue = ToastQueue()
    queue.enqueue("")
    queue.enqueue("   ")
    assert queue.current_text == ""
