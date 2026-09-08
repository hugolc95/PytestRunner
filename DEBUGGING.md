# Debugging a test

Install the optional debugger in the Python interpreter selected under
Configuration > Test Python interpreter:

```powershell
& 'C:\path\to\python.exe' -m pip install -r requirements-debug.txt
```

For offline installations, download a debugpy wheel matching that interpreter
and install it locally. It is not included in the existing offline wheel bundle.

1. Select a test (or one parametrized case) in the tree and open Source.
2. Click the line-number margin to toggle red breakpoints.
3. Click **Debug test**, then **Start debug** in the debug window.
4. While paused, inspect variables and use **Step over**, **Step into**,
   **Step out**, or **Continue**. The highlighted line is the next to execute.
5. **Stop** or closing the window terminates the debugging session.

The debug window also accepts breakpoints. Unverified breakpoints are reported
in its output. Breakpoints are retained per file for the current application
session; they are line numbers, so review their positions after editing a file.

This initial version runs one test selection on one reader, outside run history,
campaigns and reporting. Workspace environment and reader configuration are
preserved. Debug runs clear pytest `addopts` (both configuration and environment)
to avoid parallel execution and other implicit run options. Fixtures still run
normally. Variables show their immediate textual values; there is no expression
console or expandable object inspector yet. Stepping applies to Python code.
