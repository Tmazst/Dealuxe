"""
Utility functions for safe console output on VPS with latin-1 encoding
"""

def safe_print(msg):
    """
    Print to console with fallback for unicode encoding errors.
    Needed because VPS uses latin-1 encoding which can't handle card suit symbols.
    """
    try:
        print(msg)
    except UnicodeEncodeError:
        # Fallback: replace non-ASCII characters with '?'
        safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
        print(safe_msg)
