"""Expected order business rejections shared by checkout and pure pricing."""


class OrderError(Exception):
    """Adapters may map this rejection to code/message/status; input bugs stay separate."""

    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
