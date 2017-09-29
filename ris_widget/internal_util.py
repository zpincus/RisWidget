class ProxyProperty(property):
    def __init__(self, owner_name, proxied_property):
        self.owner_name = owner_name
        self.proxied_property = proxied_property
        self.__doc__ = proxied_property.__doc__

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self.proxied_property.fget(getattr(obj, self.owner_name))

    def __set__(self, obj, v):
        self.proxied_property.fset(getattr(obj, self.owner_name), v)

    def __delete__(self, obj):
        self.proxied_property.fdel(getattr(obj, self.owner_name))


class Condition:
    def __init__(self):
        self.value = False

    def __bool__(self):
        return self.value

    def __enter__(self):
        self.value = True

    def __exit__(self, exc_type, exc_value, traceback):
        self.value = False