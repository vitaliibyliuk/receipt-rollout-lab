VERSION = "v2"


def confirm(submission_id, interrupted):
    """Return a simulated receipt for a committed submission."""
    if interrupted:
        raise TimeoutError("Simulated confirmation timeout")
    return f"receipt-{submission_id:06d}"
