REM The MIT License (MIT)
REM
REM Copyright (c) 2014 Erik Hvatum
REM
REM Permission is hereby granted, free of charge, to any person obtaining a copy
REM of this software and associated documentation files (the "Software"), to deal
REM in the Software without restriction, including without limitation the rights
REM to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
REM copies of the Software, and to permit persons to whom the Software is
REM furnished to do so, subject to the following conditions:
REM
REM The above copyright notice and this permission notice shall be included in all
REM copies or substantial portions of the Software.
REM
REM THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
REM IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
REM FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
REM AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
REM LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
REM OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
REM SOFTWARE.

del ris_widget.lib
del ris_widget.exp
del ris_widget.pyd
sip -c . -b ris_widget.sbf -I D:\Installs\Python\sip\PyQt5 -x VendorID -t WS_WIN -t Qt_5_2_0 -x PyQt_SSL ris_widget.sip
icl -c -nologo -Zm200 -Zc:wchar_t -FS -O2 -MD -W3 -w34100 -w34189 -DNDEBUG -DUNICODE -DWIN32 -DWIN64 -DQT_DLL -DQT_NO_DEBUG -DQT_CORE_LIB -DQT_GUI_LIB -I. -ID:\Installs\Python\include -Id:\installs\qt5\mkspecs\win32-msvc2010 -I d:\installs\qt5\include\QtCore -Id:\installs\qt5\include\QtGui -Id:\installs\qt5\include\QtWidgets -Id:\installs\qt5\include\QtPrintSupport -Id:\installs\qt5\include -ID:\Installs\glm /Qstd=c++11 -ID:\Installs\qt5\include\QtOpenGL -I E:\zplrepo\ris_widget\cpp\GeneratedFiles *.cpp
link /NOLOGO /DYNAMICBASE /NXCOMPAT /DLL /SUBSYSTEM:WINDOWS /INCREMENTAL:NO /OUT:ris_widget.pyd *.obj E:\zplrepo\ris_widget\cpp\x64\Release\RisWidget.lib /LIBPATH:D:\Installs\Python\libs Qt5Core.lib Qt5Gui.lib Qt5OpenGL.lib Qt5OpenGLExtensions.lib Qt5Widgets.lib /LIBPATH:D:\Installs\qt5\lib