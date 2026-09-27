class HeatzyError(Exception):
    pass


class DeviceNotFound(HeatzyError):
    pass


class DeviceNotSupported(HeatzyError):
    pass


class NotConnected(HeatzyError):
    pass


class OrderFailed(HeatzyError):
    pass
