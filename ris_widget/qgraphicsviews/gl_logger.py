# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

_GL_LOGGERS = {}

def get_logger():
    context = Qt.QOpenGLContext.currentContext()
    if context is None:
        raise RuntimeError('There is no current OpenGL context.')
    assert Qt.QThread.currentThread() is context.thread()
    try:
        return _GL_LOGGERS[context]
    except KeyError:
        pass
    gl_logger = Qt.QOpenGLDebugLogger()
    if not gl_logger.initialize():
        raise RuntimeError('Failed to initialize QOpenGLDebugLogger.')
    gl_logger.messageLogged.connect(_on_gl_logger_message)
    context.destroyed.connect(_on_destroyed_context_with_gl_logger)
    gl_logger.enableMessages()
    gl_logger.startLogging(Qt.QOpenGLDebugLogger.SynchronousLogging)
    _GL_LOGGERS[context] = gl_logger
    return gl_logger

_GL_LOGGER_MESSAGE_SEVERITIES = {
    Qt.QOpenGLDebugMessage.InvalidSeverity: 'Invalid',
    Qt.QOpenGLDebugMessage.HighSeverity: 'High',
    Qt.QOpenGLDebugMessage.MediumSeverity: 'Medium',
    Qt.QOpenGLDebugMessage.LowSeverity: 'Low',
    Qt.QOpenGLDebugMessage.NotificationSeverity: 'Notification',
    Qt.QOpenGLDebugMessage.AnySeverity: 'Any'}

_GL_LOGGER_MESSAGE_SOURCES = {
    Qt.QOpenGLDebugMessage.InvalidSource: 'Invalid',
    Qt.QOpenGLDebugMessage.APISource: 'API',
    Qt.QOpenGLDebugMessage.WindowSystemSource: 'WindowSystem',
    Qt.QOpenGLDebugMessage.ShaderCompilerSource: 'ShaderCompiler',
    Qt.QOpenGLDebugMessage.ThirdPartySource: 'ThirdParty',
    Qt.QOpenGLDebugMessage.ApplicationSource: 'Application',
    Qt.QOpenGLDebugMessage.OtherSource: 'Other',
    Qt.QOpenGLDebugMessage.AnySource: 'Any'}

_GL_LOGGER_MESSAGE_TYPES = {
    Qt.QOpenGLDebugMessage.InvalidType: 'Invalid',
    Qt.QOpenGLDebugMessage.ErrorType: 'Error',
    Qt.QOpenGLDebugMessage.DeprecatedBehaviorType: 'DeprecatedBehavior',
    Qt.QOpenGLDebugMessage.UndefinedBehaviorType: 'UndefinedBehavior',
    Qt.QOpenGLDebugMessage.PortabilityType: 'Portability',
    Qt.QOpenGLDebugMessage.PerformanceType: 'Performance',
    Qt.QOpenGLDebugMessage.OtherType: 'Other',
    Qt.QOpenGLDebugMessage.MarkerType: 'Marker',
    Qt.QOpenGLDebugMessage.GroupPushType: 'GroupPush',
    Qt.QOpenGLDebugMessage.GroupPopType: 'GroupPop',
    Qt.QOpenGLDebugMessage.AnyType: 'Any'}

def _on_gl_logger_message(message):
    Qt.qDebug('GL LOG MESSAGE (severity: {}, source: {}, type: {}, GL ID: {}): "{}"'.format(
        _GL_LOGGER_MESSAGE_SEVERITIES[message.severity()],
        _GL_LOGGER_MESSAGE_SOURCES[message.source()],
        _GL_LOGGER_MESSAGE_TYPES[message.type()],
        message.id(),
        message.message()))

def _on_destroyed_context_with_gl_logger(context):
    del _GL_LOGGERS[context]
