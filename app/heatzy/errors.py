class HeatzyError(Exception):
    pass


class NotConnected(HeatzyError):
    pass


class OrderFailed(HeatzyError):
    pass
