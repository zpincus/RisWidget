// The MIT License (MIT)
//
// Copyright (c) 2014 Erik Hvatum
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

#include "Common.h"
#include "Renderer.h"
#include "ViewWidget.h"

ViewWidget::ViewWidget(QWidget* parent)
  : QWidget(parent)
{
}

ViewWidget::~ViewWidget()
{
}

View* ViewWidget::view()
{
    return m_view;
}

QWidget* ViewWidget::viewContainerWidget()
{
    return m_viewContainerWidget;
}

void ViewWidget::makeView()
{
    if(m_view || m_viewContainerWidget)
    {
        throw RisWidgetException("ViewWidget::makeView(): View already created.  makeView() must not be "
                                 "called more than once per ViewWidget instance.");
    }
    if(layout() == nullptr)
    {
        QHBoxLayout* layout_(new QHBoxLayout);
        setLayout(layout_);
    }
    m_view = instantiateView();
    m_viewContainerWidget = QWidget::createWindowContainer(m_view, this, Qt::Widget);
    layout()->addWidget(m_viewContainerWidget);
    m_viewContainerWidget->show();
    m_view->show();
}