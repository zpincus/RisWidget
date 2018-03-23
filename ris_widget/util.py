# This code is licensed under the MIT License (see LICENSE file for details)

def input(message=''):
    """Replacement for python-builtin input() which will still allow a RisWidget
    to update while waiting for input.
    """
    import IPython
    import prompt_toolkit
    ip = IPython.get_ipython()
    el = prompt_toolkit.shortcuts.create_eventloop(ip.inputhook)
    return prompt_toolkit.prompt(message, eventloop=el)
