"""Contenu du guide d'utilisation (bouton Help, F1).

Le texte vit ici, separe de la mise en page (`help_site`) : on corrige une
explication sans toucher au site, et les tests verifient chaque lien.

Le contenu est en anglais comme le reste de l'interface : l'outil est deploye a
l'international. Chaque rubrique est un fragment HTML simple ; `help_site` en
fait un site hors ligne d'un seul fichier, ouvert dans le navigateur.

Liens internes :
- ``topic:<id>`` ouvre une autre rubrique ;
- ``page:<cle>`` nomme une page de l'application (``workspace``, ``profiles``,
  ``yaml``, ``history``, ``comparison``, ``python``, ``console``,
  ``settings``) ; dans le navigateur, elle s'affiche comme un repere d'interface.

Les marqueurs ``{version}``, ``{history_dir}``... sont remplaces a l'ouverture
par les valeurs reelles du poste (voir ``help_site.support_values``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpTopic:
    id: str
    category: str
    title: str
    summary: str
    keywords: str
    body: str


def kbd(*keys: str) -> str:
    """Raccourci clavier, rendu comme une suite de touches."""
    return "<span class='keys'>" + "".join(f"<kbd>{key}</kbd>" for key in keys) + "</span>"


def tip(text: str) -> str:
    return f"<div class='callout tip'><div class='callout-title'>Tip</div><p>{text}</p></div>"


def note(text: str) -> str:
    return f"<div class='callout note'><div class='callout-title'>Important</div><p>{text}</p></div>"


CATEGORIES = (
    "Getting started",
    "Running tests",
    "Results and diagnosis",
    "Execution profiles",
    "Configuration",
    "History and reports",
    "Application",
    "Troubleshooting",
)


_TOPICS = [
    # =====================================================================
    # Getting started
    # =====================================================================
    HelpTopic(
        "welcome", "Getting started", "Welcome to Pytest Runner",
        "What the application does and how this guide is organized.",
        "overview introduction about what is tour sidebar navigation",
        f"""
<p>Pytest Runner is a desktop application that <b>collects, selects, runs and
analyzes pytest test suites</b>, including suites that run against one or more
smart-card readers (HubReader, ATR, APDU) at the same time.</p>

<h2>How it works</h2>
<p>The application never imports the code under test. It starts pytest in a
separate process with the <b>test Python interpreter</b> you choose, and reads
its results live. This means:</p>
<ul>
<li>the application and the tests can use two different Python installations
(for example a 32-bit test environment for native DLLs);</li>
<li>a crash in a test, a DLL or a reader driver cannot take the application
down: it is reported as a result instead;</li>
<li>your tests run exactly as they would from the command line.</li>
</ul>

<h2>The sidebar</h2>
<table>
<tr><th>Page</th><th>Use it to</th></tr>
<tr><td><a href="page:workspace">Run Tests</a></td><td>Load a workspace, select tests, choose readers, run and read the results.</td></tr>
<tr><td><a href="page:profiles">Execution Profiles</a></td><td>Build ordered, reusable test sequences with groups and per-test YAML parameters.</td></tr>
<tr><td><a href="page:yaml">YAML Configuration</a></td><td>Edit the configuration (readers, log folder, interpreter…) of each run.</td></tr>
<tr><td><a href="page:history">History</a></td><td>Browse every recorded run, re-run it, export HTML / JUnit reports.</td></tr>
<tr><td><a href="page:comparison">Comparison</a></td><td>Compare verdicts across several historical runs.</td></tr>
<tr><td><a href="page:python">Python Environment</a></td><td>Choose and verify the Python interpreter that runs the tests.</td></tr>
<tr><td><a href="page:console">Console</a></td><td>See the real commands, process output and errors of the session.</td></tr>
<tr><td><b>Help</b></td><td>This guide, in your web browser. Press {kbd("F1")} anywhere to open the topic of the current page.</td></tr>
<tr><td><a href="page:settings">Settings</a></td><td>Personal preferences: theme, text size, timeouts, editor…</td></tr>
</table>

<h2>Where to start</h2>
<p>New users should read <a href="topic:quick-start">Your first run in five
steps</a>. If something does not work, go straight to
<a href="topic:troubleshooting">Troubleshooting</a>.</p>
{tip(f"Press {kbd('Ctrl', 'K')} or click <b>Search the guide</b> at the top: every topic that mentions your words is listed instantly. The guide works offline, can be printed or saved as PDF, and can be shared as a single file.")}
""",
    ),
    HelpTopic(
        "quick-start", "Getting started", "Your first run in five steps",
        "From an empty window to your first results.",
        "first run start begin tutorial steps beginner",
        f"""
<ol class='steps'>
<li><b>Check the test interpreter.</b> Open <a href="page:python">Python
Environment</a>, select the <code>python.exe</code> that has pytest installed
and click <b>Test</b>. When the check succeeds, click <b>Save</b>.
See <a href="topic:python-env">Python Environment</a>.</li>
<li><b>Load a workspace.</b> On <a href="page:workspace">Run Tests</a>, type or
paste the folder of your tests in the workspace field, or click <b>Browse</b>.
The tests are collected automatically; <b>Collect</b> or {kbd("Ctrl", "R")}
collects again. See <a href="topic:workspace">Workspaces and collection</a>.</li>
<li><b>Select the tests.</b> Tick tests, files or folders in the tree. Use
<b>Find a test…</b> ({kbd("Ctrl", "F")}) or the marker filter
({kbd("Ctrl", "M")}) for large suites. See
<a href="topic:selecting">Selecting tests</a>.</li>
<li><b>Choose the readers</b> (only for suites that use readers). In
<b>EXECUTION</b>, pick the primary reader and, if needed, tick additional
readers.
See <a href="topic:readers">Readers and ATR</a>.</li>
<li><b>Run.</b> Click <b>Run tests</b> or press {kbd("F5")}. The progress ring
and the counters update live, results appear in the tree; select a test to read its detail, output and logs. See
<a href="topic:results">Reading the results</a>.</li>
</ol>
{tip("Every run is saved automatically in History, with its configuration, logs and verdicts. You can close the application without losing anything that has finished.")}
""",
    ),
    HelpTopic(
        "requirements", "Getting started", "Installation and requirements",
        "What must be installed on the workstation.",
        "install installation requirements setup prerequisites pytest xdist exe windows 32 64 bit",
        f"""
<h2>The application</h2>
<p>Pytest Runner is distributed as a Windows folder (<code>PytestRunner\\</code>)
that contains <code>PytestRunner.exe</code> and its libraries. Copy the
<b>whole folder</b>, not only the <code>.exe</code>. No Python installation is
needed to start the application itself.</p>

<h2>The test environment</h2>
<p>The tests run with a Python interpreter installed on the workstation. That
interpreter needs:</p>
<table>
<tr><th>Package</th><th>Required</th><th>Why</th></tr>
<tr><td><code>pytest</code></td><td>Yes</td><td>Collects and runs the tests.</td></tr>
<tr><td><code>pytest-xdist</code></td><td>Optional</td><td>Only for parallel execution inside one reader.</td></tr>
<tr><td>Your project dependencies</td><td>Yes</td><td>Whatever your tests import (reader libraries, DLL wrappers…).</td></tr>
</table>
<p>The test interpreter can be 32-bit or 64-bit, independently of the
application. Choose it in <a href="page:python">Python Environment</a>, or set
<code>python_executable</code> in the workspace YAML.</p>

<h2>Readers</h2>
<p>Reader suites need the reader drivers and the libraries your tests already
use. Pytest Runner lists the connected HubReader devices automatically and
also accepts reader names typed manually.</p>
{note("Install the same test environment on every workstation that runs a given suite. A different pytest or library version can change the results.")}
""",
    ),

    # =====================================================================
    # Running tests
    # =====================================================================
    HelpTopic(
        "run-tests", "Running tests", "The Run Tests page",
        "The three panels at the top, the test tree and the result panel.",
        "run tests page layout environment execution results panel tree overview",
        f"""
<p>The <a href="page:workspace">Run Tests</a> page is where most of the work
happens. From top to bottom:</p>

<h2>Run tabs</h2>
<p>Each run lives in its own tab. <b>+ New run</b> prepares another selection
while a run is executing; runs started during an execution wait in a queue.
See <a href="topic:run-tabs">Run tabs and queue</a>.</p>

<h2>ENVIRONMENT</h2>
<p>The workspace folder, <b>Browse</b>, <b>Collect</b> and the optional
<b>Run name</b>. The run name appears in the tab, in History and in reports;
leave it empty for an automatic run number.</p>

<h2>EXECUTION</h2>
<p><b>Run tests</b> ({kbd("F5")}), <b>Pause</b>, <b>Stop</b> ({kbd("Esc")}),
<b>Re-run failed</b> ({kbd("F6")}), the primary reader with its ATR, the
additional readers, and the icon that opens this run's YAML configuration.
When a profile is loaded, a chip shows its name; its <b>×</b> unloads it.</p>

<h2>RESULTS</h2>
<p>The progress ring, the five counters <b>Passed</b>, <b>Failed</b>,
<b>Skipped</b>, <b>Error</b>, <b>Not run</b>, and the shortcuts <b>View
failures</b> and <b>View differences</b>. Clicking a counter shows only those
tests; clicking it again shows all tests.</p>

<h2>Test tree and result panel</h2>
<p>On the left, the test tree, with the tabs <b>All tests</b> and
<b>Profiles</b>. On the right, the result panel with <b>Detail</b>,
<b>Source</b>, <b>Output</b> and <b>Logs</b>. The separator between them can be
dragged. The status bar at the bottom shows the collection and run status,
the elapsed time and the background saves.</p>
{tip("In a small window the three top panels stack and the sidebar collapses to icons. Every control stays available.")}
""",
    ),
    HelpTopic(
        "workspace", "Running tests", "Workspaces and collection",
        "Loading a folder of tests, collecting, collection errors.",
        "workspace folder load browse collect collection reload ctrl+r error incomplete conftest import syntax recent",
        f"""
<h2>Load a workspace</h2>
<p>A workspace is the folder that contains your tests (usually the folder with
<code>pytest.ini</code>, <code>pyproject.toml</code> or <code>conftest.py</code>).
Type or paste its path in <b>ENVIRONMENT</b>, choose a recent workspace from the
list, or click the folder icon. Collection starts automatically.</p>
<p>If the path is invalid, the field returns to the workspace that is actually
loaded: you cannot run tests of an old project in a new folder by mistake.</p>

<h2>Collect again</h2>
<p>Click the refresh icon or press {kbd("Ctrl", "R")} after adding, renaming or
deleting tests. Running a test that no longer exists makes pytest refuse the
whole command: the <b>Execution error</b> window explains it and asks you to
collect again.</p>

<h2>Collection errors</h2>
<ul>
<li><b>A file cannot be imported</b> (syntax error, missing import): the other
files are still collected and can be run. The file appears in the tree in the
error colour, without a checkbox. Select it to read the error in
<b>Detail</b>; the status bar shows <i>N file(s) could not be collected</i>.</li>
<li><b>A <code>conftest.py</code> fails, or no file is valid</b>: the collection
stops and a window shows the number of errors, the file and line, and the full
tracebacks. <b>Copy errors</b> copies the diagnosis; <b>Show console</b> opens
the <a href="topic:console">Console</a> on the errors.</li>
<li><b>Timeout</b>: collection stops after the time set in
<a href="topic:settings">Settings → Timeouts</a> (120 s by default).</li>
</ul>
<p>A run whose collection was incomplete is marked <b>Incomplete</b> in orange,
even if every executed test passed, and the warning is kept in History and in
reports.</p>

<h2>YAML configuration of the workspace</h2>
<p>When the workspace contains YAML files, the configuration is detected
automatically (<code>config.yaml</code> / <code>config.yml</code> first). Each
run tab works on its own copy. See
<a href="topic:yaml-config">YAML configuration</a>.</p>
""",
    ),
    HelpTopic(
        "selecting", "Running tests", "Selecting tests",
        "Checkboxes, search, markers, parametrized cases and quick selections.",
        "select selection checkbox tick search find filter marker ctrl+m ctrl+a parametrized parameter case divergent disagree",
        f"""
<h2>Tick tests</h2>
<p>Tick a folder, a file, a class, a test function or a single parametrized
case. Ticking a parent ticks everything below it; a dash means a partial
selection. Only the ticked tests run.</p>
<p>Parametrized tests (<code>@pytest.mark.parametrize</code>) show each case as
a separate leaf such as <code>[small]</code>, <code>[medium]</code>: you can
run a single case.</p>

<h2>Quick selections</h2>
<table>
<tr><th>Action</th><th>Shortcut</th></tr>
<tr><td>Select all</td><td>{kbd("Ctrl", "A")}</td></tr>
<tr><td>Clear selection</td><td>{kbd("Ctrl", "Shift", "A")}</td></tr>
<tr><td>Only tests where readers disagree</td><td>{kbd("Ctrl", "D")}</td></tr>
<tr><td>Find a test</td><td>{kbd("Ctrl", "F")}</td></tr>
<tr><td>Filter by marker</td><td>{kbd("Ctrl", "M")}</td></tr>
</table>

<h2>Find a test</h2>
<p><b>Find a test…</b> above the tree filters it by name. {kbd("Esc")} in this
field clears the search.</p>

<h2>Markers</h2>
<p>The <b>Markers</b> icon ({kbd("Ctrl", "M")}) lists the pytest markers of the
workspace. Choose markers or type an expression such as
<code>smoke and not slow</code>: the matching tests are selected. Removing the
filter keeps the selection. The marker filter is locked during a run.</p>

<h2>Show only some results</h2>
<p>Click a counter (<b>Failed</b>, <b>Skipped</b>…) in RESULTS to show only
those tests. Click it again to show everything.</p>
{tip("Deactivated tests stay visible with the ⊘ symbol and cannot be ticked. See <a href='topic:disabled-tests'>Deactivating tests</a>.")}
""",
    ),
    HelpTopic(
        "running", "Running tests", "Running, pausing and stopping",
        "Run, Pause / Resume, Stop, Re-run failed, targeted runs and repetitions.",
        "run start f5 pause resume stop esc rerun re-run failed f6 run only this run n times until it fails repeat stress queue",
        f"""
<h2>Run</h2>
<p><b>Run tests</b> or {kbd("F5")} runs the ticked tests on the selected readers.
If another run is executing, the button becomes <b>Add to queue</b>: the
selection, readers and configuration are captured, and the run starts when the
previous one has finished. See <a href="topic:run-tabs">Run tabs and queue</a>.</p>

<h2>Pause and resume</h2>
<p>During a run, <b>Pause</b> replaces <b>Run</b>. The test that is executing
finishes normally, including its setup and teardown; the status shows
<i>Pause requested — waiting for the current test to finish</i>, then
<i>Paused</i>. <b>Resume</b> continues with the next test in the same pytest
session, without running the previous tests again. <b>Cancel pause</b> cancels a
pause that has not happened yet. Keep the application open while paused.</p>

<h2>Stop</h2>
<p><b>Stop</b> or {kbd("Esc")} stops the run. {kbd("Esc")} is ignored while the
cursor is in a text field, so you never stop a run while typing; the
<b>Stop</b> button always works. Tests that were requested but not executed are
counted as <b>Not run</b>, never as passed or failed.</p>

<h2>Re-run failed</h2>
<p><b>Re-run failed</b> or {kbd("F6")} runs again the tests that failed, raised
an error or were not run in the last run. When some tests were not run, the
button reads <b>Re-run incomplete</b>.</p>

<h2>Right-click on a test or a group</h2>
<table>
<tr><th>Command</th><th>Effect</th></tr>
<tr><td>Run only this test / Run only this</td><td>Runs this test or group without changing the ticked tests. The verdicts of the other tests stay visible.</td></tr>
<tr><td>Run N times…</td><td>Runs one test N times in a row (20 by default) and shows a dedicated summary.</td></tr>
<tr><td>Run until it fails…</td><td>Repeats one test until it fails, with a safety limit of 50 runs. Useful to catch intermittent failures.</td></tr>
<tr><td>Copy nodeid</td><td>Copies the pytest identifier, ready for the command line.</td></tr>
<tr><td>Copy failure trace</td><td>Copies the last known failure of the test.</td></tr>
<tr><td>Open file</td><td>Opens the test in the <b>Source</b> tab.</td></tr>
<tr><td>Deactivate test… / group…</td><td>See <a href="topic:disabled-tests">Deactivating tests</a>.</td></tr>
</table>
<p>During <b>Run N times</b> and <b>Run until it fails</b>, the <b>Repeat</b>
banner shows completed repetitions, readers, executions and verdicts. These
series appear in History with the origin <b>REPEAT</b>.</p>
""",
    ),
    HelpTopic(
        "readers", "Running tests", "Readers and ATR",
        "Primary reader, additional readers, parallel or sequential, ATR.",
        "reader readers hubreader card smart card atr apdu primary additional parallel sequential reader_mode discovery color badge",
        f"""
<h2>Primary reader</h2>
<p>In <b>EXECUTION</b>, the <b>Reader</b> list shows the HubReader devices
detected on the workstation and the readers declared in the YAML. Opening the
list searches again, so a reader plugged in a moment ago appears. You can also
type a reader name manually. Discovery stops after the time set in
<a href="topic:settings">Settings → Timeouts</a>; manual entry always remains
available.</p>

<h2>Additional readers</h2>
<p>Use <b>Readers</b> to add readers to the next run. Each reader runs the
same selection in its own pytest process, and each reader gets its own colour
in the tree, the output tabs, the logs and the reports.</p>

<h2>Parallel or one reader at a time</h2>
<p>By default all readers run <b>together</b>. Set
<code>reader_mode: sequential</code> in the YAML to run them one after the
other; the reader controls then show <i>one reader at a time</i>.</p>

<h2>How a test knows its reader</h2>
<p>The tests keep reading the <code>Reader</code> key of the configuration as
usual. Pytest Runner presents to each pytest process a configuration in which
<code>Reader</code> already has the right value, without writing anything to
disk. The reader name is also available in the environment variable
<code>PYTESTRUNNER_READER</code>.</p>

<h2>ATR</h2>
<p>The ATR of the card in the primary reader is shown next to the reader. The
field is selectable so you can copy it; the refresh icon reads the card again.
<a href="topic:settings">Settings → Interface → ATR in the bottom bar</a> moves
it to the status bar. Reader discovery and ATR polling are suspended during a
run so that they never disturb the tests.</p>

<h2>Comparing readers</h2>
<p>When readers disagree on a test, <b>View differences</b> and
{kbd("Ctrl", "D")} find those tests, and <b>Compare</b> in the Logs tab
({kbd("Ctrl", "Shift", "D")}) shows their logs side by side. See
<a href="topic:details">Detail, Source, Output and Logs</a>.</p>
""",
    ),
    HelpTopic(
        "run-tabs", "Running tests", "Run tabs and queue",
        "Several runs, queue, rename, duplicate, detach.",
        "tab tabs new run queue add to queue pause queue rename duplicate detach reattach live draft",
        f"""
<h2>Several runs</h2>
<p><b>+ New run</b> creates a draft tab with the same collected tests, unticked.
Each tab has its own selection, readers, YAML copy, results and status bar.
You can prepare the next run while another one is executing.</p>

<h2>Queue</h2>
<p>Only one run executes at a time. While a run is executing, <b>Run tests</b>
becomes <b>Add to queue</b>; the selection, readers, environment, options and
YAML are captured at that moment. Waiting runs start one after the other.
<b>Pause queue</b> lets the current run finish and holds the next ones.
Drag the tabs to change the order of waiting runs.</p>

<h2>Tab colours</h2>
<table>
<tr><th>Colour</th><th>Meaning</th></tr>
<tr><td>Blue</td><td>Running</td></tr>
<tr><td>Amber</td><td>Waiting in the queue</td></tr>
<tr><td>Green</td><td>Finished successfully</td></tr>
<tr><td>Red</td><td>Finished with failures, or stopped</td></tr>
</table>
<p>When another tab is displayed, <b>Live</b> returns to the executing run.</p>

<h2>Tab menu (right-click)</h2>
<ul>
<li><b>Rename run…</b> — changes the tab and window title;</li>
<li><b>Duplicate as a new draft</b> — copies the selection and settings;</li>
<li><b>Remove from queue and edit</b> — takes a waiting run back to change it;</li>
<li><b>Edit run configuration…</b> — opens this run's YAML copy;</li>
<li><b>Detach tab</b> / <b>Reattach tab</b> — shows the run in a separate window, for example on a second screen;</li>
<li><b>Close tab</b>.</li>
</ul>
{note("Drafts, tab names and window positions are restored at the next start. A run that was executing or waiting reopens as a draft: the application never starts a run on its own after a restart.")}
""",
    ),
    HelpTopic(
        "disabled-tests", "Running tests", "Deactivating tests",
        "Temporarily exclude a test or a group from every run.",
        "deactivate disable disabled activate exclude ignore skip reason group",
        f"""
<p>Right-click a test → <b>Deactivate test…</b>, or a folder, file, class or
parametrized test → <b>Deactivate group…</b>. The reason is optional but helps
your colleagues (for example <i>destructive test — do not erase the card
again</i>). For a parametrized case you can deactivate this case only, or all
cases of the test including future parameters.</p>
<ul>
<li>The ⊘ symbol replaces the test icon. Deactivated tests stay visible and
cannot be ticked.</li>
<li>They are excluded before execution: no fake <i>skipped</i> verdict is
created.</li>
<li>A group rule also covers tests added later to the group. A single test can
be reactivated inside a deactivated group.</li>
<li>Profiles that contain a deactivated step are blocked, and waiting runs are
checked again before they start.</li>
</ul>
<p>The ⊘ button in the tree toolbar appears when deactivations exist. It opens
<b>Deactivated tests</b> with the reason, the date, the author and a checkbox to
reactivate each item; <b>Activate all</b> and <b>Deactivate all</b> act on the
whole list.</p>
{note("Deactivations are stored for each workspace in this user's application data. They do not modify any test file and only apply to runs started from Pytest Runner.")}
""",
    ),

    # =====================================================================
    # Results and diagnosis
    # =====================================================================
    HelpTopic(
        "results", "Results and diagnosis", "Reading the results",
        "Verdicts, counters, progress, Incomplete, durations.",
        "result results verdict passed failed skipped error not run running counter progress ring incomplete duration column slowest fastest spread icon",
        f"""
<h2>Verdicts</h2>
<table>
<tr><th>Verdict</th><th>Meaning</th></tr>
<tr><td><b>Passed</b></td><td>The test succeeded.</td></tr>
<tr><td><b>Failed</b></td><td>An assertion or an exception failed in the test itself.</td></tr>
<tr><td><b>Error</b></td><td>The failure happened in a fixture (setup or teardown), not in the test body.</td></tr>
<tr><td><b>Skipped</b></td><td>The test was skipped by pytest (<code>skip</code>, <code>skipif</code>, <code>xfail</code>…).</td></tr>
<tr><td><b>Not run</b></td><td>The test was requested but never executed: run stopped, process crash, collection problem. The reason is shown in Detail.</td></tr>
</table>
<p>A test shown in <b>blue</b> is running, together with its parent groups.
<b>Preparing</b> means the pytest process is starting and collecting.</p>

<h2>Counters and progress</h2>
<p>The five counters of RESULTS count the tests actually executed in this run.
Failures and errors are always counted separately. Click a counter to show
only those tests. The progress ring and the <b>X / Y</b> counter follow the run
or the active profile.</p>

<h2>Overall verdict</h2>
<p>A run is <b>Incomplete</b> (orange) when some files could not be collected,
or when part of a campaign was not executed, even if every executed test
passed. The <b>files not collected</b> button lists the errors.</p>

<h2>With several readers</h2>
<p>Each reader has its own column in the tree. <b>View differences</b> and
{kbd("Ctrl", "D")} find the tests where readers disagree.</p>

<h2>Duration column</h2>
<p>The duration (setup + call + teardown) appears as soon as each test ends.
Right-click the column headers → <b>Duration shows</b>: <i>Slowest</i> reader
(default), <i>Fastest</i>, <i>Average</i>, <i>Spread</i> between slowest and
fastest, or one reader. In <i>Spread</i> mode a notable gap is shown in amber.
The same menu offers <b>Show Duration column</b> and <b>Reset column
widths</b>. Column widths you set with the mouse are remembered.</p>

<h2>Keeping previous results</h2>
<p>With <a href="topic:settings">Settings → Tree &amp; details → Keep previous
results in the test tree</a>, the last known verdict of every test stays in the
tree: filled icons come from the latest run, outlined icons from earlier runs.
The eraser <b>Clear tree results</b> resets the tree without touching
History.</p>
""",
    ),
    HelpTopic(
        "details", "Results and diagnosis", "Detail, Source, Output and Logs",
        "The result panel, tracebacks, source editing, log search and comparison.",
        "detail source output logs tab traceback trace link editor vscode pycharm log search find compare comparison f7 ctrl+1 ctrl+2 ctrl+3 ctrl+4 wrap",
        f"""
<p>Select a test, a file or a folder in the tree to fill the result panel.
The tab you were reading stays open when you select another test (see
<i>Tab when selecting another test</i> in Settings).</p>

<h2>Detail ({kbd("Ctrl", "1")})</h2>
<p>The verdict of every reader, the duration, the skip reason and the
tracebacks of the setup, the call and the teardown. Details arrive live, while
the next tests are still running. For a folder or a file, Detail shows a
summary per reader with links to the tests concerned.</p>
<p>File and line references are <b>links</b>: a click opens the file in
<b>Source</b> at the right line; <b>Back to traceback</b> returns. A
{kbd("Ctrl")}+click opens it in your external editor (VS Code or PyCharm,
see <a href="topic:settings">Settings → External editor</a>). Right-click a
link for <b>Copy file:line</b> and <b>Locate file…</b>.</p>

<h2>Source ({kbd("Ctrl", "2")})</h2>
<p>The test file, with syntax colouring, opened at the test. It can be edited
and saved with {kbd("Ctrl", "S")} when no run is active.</p>

<h2>Output ({kbd("Ctrl", "3")})</h2>
<p>Everything pytest wrote, per reader, with its colours. {kbd("Ctrl", "A")}
selects the text of the panel.</p>

<h2>Logs ({kbd("Ctrl", "4")})</h2>
<p>The <code>.log</code> files written by the tests for the selected test,
per reader. Timestamps at the start of lines are hidden for readability;
the files on disk are unchanged. <b>Open log</b> opens the full file.</p>
<table>
<tr><th>Search in a log</th><th>Keys</th></tr>
<tr><td>Go to the search field</td><td>{kbd("Ctrl", "F")} (from the log)</td></tr>
<tr><td>Next / previous match</td><td>{kbd("Enter")} or {kbd("F3")} / {kbd("Shift", "Enter")} or {kbd("Shift", "F3")}</td></tr>
<tr><td>Clear the search</td><td>{kbd("Esc")}</td></tr>
</table>
<p>The red arrows jump between errors in the log.</p>

<h2>Comparing readers</h2>
<p><b>Compare…</b> ({kbd("Ctrl", "Shift", "D")}) opens the logs of every reader
side by side in a separate window that you can move to another screen.
{kbd("F7")} / {kbd("Shift", "F7")} jump to the next / previous difference;
{kbd("Ctrl", "W")} closes the window. Untick <b>Follow selected test</b> to
freeze the comparison; <b>Load selected test</b> loads another one. The layout
can be <i>Automatic</i>, <i>Side by side</i> or <i>Stacked</i>.</p>
""",
    ),
    HelpTopic(
        "native-crash", "Results and diagnosis", "Crashes and tests not run",
        "What happens when pytest, a DLL or a driver crashes.",
        "crash native segfault access violation exit code windows process died not run reason",
        f"""
<p>Because pytest runs in a separate process, a native crash (access violation
in a DLL, reader driver failure, Python crash) never closes Pytest Runner.</p>
<ul>
<li>The crash is attached to the test that was running, with the Windows exit
code and the traces that were available.</li>
<li>The tests that were requested but never executed are marked
<b>Not run</b>, with their reason in Detail, History and reports.</li>
<li>The other readers continue: each reader has its own process.</li>
</ul>
<p>To investigate, read <b>Detail</b> and <b>Output</b> of the crashed test,
then the <a href="topic:console">Console</a> (category <i>Errors</i>). Use
<b>Run until it fails…</b> to reproduce an intermittent crash.</p>
""",
    ),

    # =====================================================================
    # Execution profiles
    # =====================================================================
    HelpTopic(
        "profiles", "Execution profiles", "Execution profiles",
        "Reusable, ordered test sequences: create, save, share and run.",
        "profile profiles execution sequence campaign create save import export share run profile load",
        f"""
<p>An execution profile is an <b>ordered sequence of tests</b>, saved and
reusable. Unlike the tree of Run Tests, a profile can contain the same test
several times, in any order, with its own YAML parameters at each occurrence,
organized in coloured groups.</p>

<h2>Create a profile</h2>
<ol class='steps'>
<li>Open <a href="page:profiles">Execution Profiles</a> and click <b>New
profile</b>.</li>
<li>Click <b>Add tests / groups</b>, tick tests or whole folders, then
<b>Add selected</b>.</li>
<li>Organize the sequence (see <a href="topic:profile-editing">Editing a test
sequence</a>) and set parameters (see <a href="topic:profile-yaml">Per-test
YAML parameters</a>).</li>
<li>Click <b>Save</b> or <b>Save as…</b>.</li>
</ol>

<h2>Run a profile</h2>
<p>Click <b>Open in Run Tests</b>. The <b>Profiles</b> tab of the tree shows
the sequence with its groups; the chip in EXECUTION shows the profile name.
Tick or untick occurrences, then <b>Run profile</b>. Only ticked occurrences
run, in their order and with their own YAML; the other occurrences keep their
previous results. Opening a profile while the current tab is running creates a
new draft automatically.</p>

<h2>Share a profile</h2>
<p><b>Export</b> writes the profile to a file that a colleague can
<b>Import</b>. A run in History can also be exported as a profile
(<i>Export as execution profile…</i>).</p>
{tip("Profiles created with a recent version may require that version or a later one. Deploy the same version of Pytest Runner to everyone who shares profiles.")}
""",
    ),
    HelpTopic(
        "profile-editing", "Execution profiles", "Editing a test sequence",
        "Adding, grouping, moving, copying, deleting, undo and redo.",
        "add tests groups add selected again group subgroup create group color description move drag drop duplicate remove delete copy paste ctrl+c ctrl+v undo redo ctrl+z ctrl+y move to ungroup",
        f"""
<h2>Add tests</h2>
<p><b>Add tests / groups</b> opens a picker. The insertion point follows the
selection: inside the selected group, after the selected test, or at the end
of the profile. Right-click → <b>Add tests / groups…</b> inserts at the clicked
point. <b>Add selected again</b> repeats the last addition. New tests inherit
the YAML of their parent groups.</p>

<h2>Groups</h2>
<p>Select tests (with {kbd("Ctrl")} or {kbd("Shift")}) then <b>Create
group…</b>: give it a name, a colour and a short description. Groups can contain
<b>subgroups</b> (<b>Create subgroup…</b>). <b>Edit group…</b> changes them and
<b>Ungroup</b> removes the group but keeps its tests and their parameters.</p>

<h2>Move</h2>
<p>Use the arrows, drag and drop, or right-click → <b>Move to…</b>, which lets you
choose the destination and shows the parameter changes before confirming.
Moving to another group asks for confirmation because the inherited YAML may
change.</p>

<h2>Copy, paste, duplicate, remove</h2>
<table>
<tr><th>Action</th><th>Shortcut</th></tr>
<tr><td>Copy the selection</td><td>{kbd("Ctrl", "C")}</td></tr>
<tr><td>Paste after the selection</td><td>{kbd("Ctrl", "V")}</td></tr>
<tr><td>Paste into the selected group</td><td>{kbd("Ctrl", "Shift", "V")}</td></tr>
<tr><td>Remove the selection</td><td>{kbd("Del")}</td></tr>
<tr><td>Undo / redo</td><td>{kbd("Ctrl", "Z")} / {kbd("Ctrl", "Y")}</td></tr>
</table>
<p>Copies keep the hierarchy, colours, descriptions and explicit YAML values.
Pasted items are selected and highlighted for a few seconds. Undo keeps the
last 50 actions of the current profile, even after saving.</p>
{tip("Copying to another application pastes the pytest identifiers as text.")}
""",
    ),
    HelpTopic(
        "profile-yaml", "Execution profiles", "Per-test YAML parameters",
        "Customize the configuration of one test, a group or the whole profile.",
        "yaml parameters custom value profile value inherited effective mixed values amber dot override group default reset",
        f"""
<p>Each occurrence of a test in a profile can use its own configuration
values, without changing the workspace YAML file.</p>

<h2>Inheritance</h2>
<p>Values are resolved in this order, the last one wins:</p>
<p class='center'><b>profile → parent groups → subgroup → test</b></p>
<p>For example, duplicate a group of T0 tests and set the copied group to T1:
both copies keep independent parameters.</p>

<h2>Edit parameters</h2>
<p>Select a test, a parametrized function, a folder or a group, then
<b>Edit YAML parameters…</b> (or double-click a test). For each parameter,
choose <b>Profile value</b> or <b>Custom value</b>; <b>Value used</b> shows the
result. <b>Apply</b> validates, <b>Cancel</b> abandons, <b>Reset all to profile
values</b> removes the customizations.</p>
<ul>
<li><b>Mixed values — unchanged</b>: the selected tests have different values;
only the fields you change are applied to all of them.</li>
<li><b>Custom values only</b> lists the parameters customized here.</li>
<li>A small <b>amber dot</b> on an icon marks explicit customizations; hover it
to see the value used and the inherited value.</li>
<li>A <b>warning triangle</b> means a real YAML problem (file unreadable,
invalid syntax); hover it for the diagnosis.</li>
</ul>

<h2>View the effective YAML</h2>
<p>Right-click → <b>View effective YAML…</b> shows the final values and their
origin, and the complete YAML that the test will receive.</p>
""",
    ),
    HelpTopic(
        "campaign-update", "Execution profiles", "Keeping profiles up to date",
        "What happens when tests are added, removed or parametrized.",
        "campaign update sync synchronize new tests removed parametrized contents follow source undo update keep selected cases",
        f"""
<p>When a collection finds that the workspace changed (new tests, removed
tests, a test that became parametrized), Pytest Runner proposes a global
update of the profile instead of asking for a decision per test.</p>
<ul>
<li>A simple test that became parametrized is replaced by its cases at
<b>each</b> of its calls, keeping the order, the groups and the YAML.</li>
<li><b>Contents…</b> distinguishes a <i>fixed selection</i> of precise cases
from a folder or function that <i>follows new tests</i>.</li>
<li><b>Undo update</b> works even after a restart.</li>
<li>A partially executed campaign shows <b>Campaign incomplete</b> in the
interface, History and the HTML report.</li>
</ul>
{tip("To freeze a single parametrized case that was saved as a followed function: select the case, open Contents…, choose Keep selected cases, then save.")}
""",
    ),

    # =====================================================================
    # Configuration
    # =====================================================================
    HelpTopic(
        "yaml-config", "Configuration", "YAML configuration",
        "The configuration of each run and the keys Pytest Runner understands.",
        "yaml config configuration file config.yaml reader readers reader_mode log_directory log_path incremental_log python_executable import_mode pythonpath edit import copy",
        f"""
<p><a href="page:yaml">YAML Configuration</a> shows the configuration of each
run tab, with a form and a text editor. <b>Every tab works on its own
copy</b>: editing a draft never changes the source file or the other tabs.
The same copy is used for collection and execution. <b>Import YAML…</b> copies
another file into the run. Queued and running tabs are locked.</p>

<h2>Keys understood by Pytest Runner</h2>
<p>Key names ignore case, dashes and spaces; they can be at the root or in a
section.</p>
<table>
<tr><th>Key</th><th>Role</th></tr>
<tr><td><code>Reader</code></td><td>The primary reader the tests read.</td></tr>
<tr><td><code>Readers</code></td><td>Extra readers to test with (list).</td></tr>
<tr><td><code>reader_mode</code></td><td><code>sequential</code> runs readers one after the other. Empty: together.</td></tr>
<tr><td><code>log_directory</code> / <code>log_path</code></td><td>Folder where the tests write one <code>.log</code> per test. Relative to the workspace or absolute.</td></tr>
<tr><td><code>incremental_log</code></td><td><code>true</code>: repeated executions are numbered in the same folder instead of one folder per run.</td></tr>
<tr><td><code>python_executable</code></td><td>Python used to collect and run this workspace. Has priority over the global setting.</td></tr>
<tr><td><code>import_mode</code></td><td>pytest import mode. <code>importlib</code> accepts test files with the same name in different folders.</td></tr>
<tr><td><code>pythonpath</code></td><td>Folders added to the tests' <code>PYTHONPATH</code>.</td></tr>
</table>

<h2>Example</h2>
<pre>Reader: OMNIKEY 3x21 Reader 0
Readers:
  - OMNIKEY 3x21 Reader 1
reader_mode: parallel
log_directory: logs
python_executable: C:\\Python312\\python.exe</pre>
{note("History keeps a read-only snapshot of the YAML used by each run, so later edits never change what was archived.")}
""",
    ),
    HelpTopic(
        "python-env", "Configuration", "Python Environment",
        "Choosing and verifying the Python interpreter of the tests.",
        "python interpreter environment python.exe pytest version 32 64 bit venv virtualenv save test priority global",
        f"""
<p>The application and the tests use <b>two independent Python
installations</b>. The test interpreter must have pytest and your project
dependencies.</p>

<h2>Choose the interpreter</h2>
<ol class='steps'>
<li>Open <a href="page:python">Python Environment</a>.</li>
<li>Browse to the <code>python.exe</code> of the test environment (for a
virtual environment: <code>.venv\\Scripts\\python.exe</code>).</li>
<li>Click <b>Test</b>: the version, the architecture and pytest are checked
in the background.</li>
<li><b>Save</b> becomes available only once the check succeeds.</li>
</ol>
<p>An interpreter that does not exist or has no pytest is reported as
<b>Python interpreter not usable</b>, and a banner on Run Tests offers
<b>Open configuration</b>. Changing the interpreter during a collection
restarts the collection with the new environment.</p>

<h2>Priority</h2>
<ol class='steps'>
<li><code>python_executable</code> in the workspace YAML;</li>
<li>the global setting of this page;</li>
<li>otherwise, the default Python of the workstation.</li>
</ol>
""",
    ),

    # =====================================================================
    # History and reports
    # =====================================================================
    HelpTopic(
        "history", "History and reports", "History",
        "Every recorded run: search, filter, re-run, rename, export, delete.",
        "history run runs archive search filter with issues readers workspace rerun re-run rename logs delete clear protected lock unstable flaky export ctrl+h",
        f"""
<p><a href="page:history">History</a> ({kbd("Ctrl", "H")}) lists every run,
newest first, with its readers, verdicts and origin (Run Tests, profile,
REPEAT…). Runs are saved automatically in the background when they end; a
discreet indicator in the status bar shows saves in progress.</p>

<h2>Find a run</h2>
<p>Search by run, test or reader name; filter by workspace and readers;
<b>With issues</b> shows only runs with failures or errors. <b>Clear
filters</b> resets everything.</p>

<h2>Read a run</h2>
<p>Select a run to see its executed tests, failures, durations, logs and the
YAML configuration used at launch (read-only). <b>Logs</b> opens the log
folder of the run. <b>Re-run</b> runs the same selection again; if needed the
workspace is loaded first. The pencil renames the run.</p>

<h2>Keep and clean</h2>
<ul>
<li>The lock icon <b>protects</b> a run: it is kept by <b>Clear history</b>.</li>
<li><b>Delete run</b> deletes the selected run; <b>Clear history</b> deletes all
unprotected runs.</li>
<li><b>Unstable tests</b> lists tests whose verdict changes between runs
(flaky tests).</li>
</ul>

<h2>Export</h2>
<table>
<tr><th>Menu entry</th><th>Result</th></tr>
<tr><td>Export complete HTML report…</td><td>One report with every reader of the run. See <a href="topic:reports">HTML reports</a>.</td></tr>
<tr><td>Export HTML… (per reader)</td><td>A report for one reader.</td></tr>
<tr><td>Export JUnit XML… (per reader)</td><td>For CI tools and test managers.</td></tr>
<tr><td>Export as execution profile…</td><td>Turns the run into a reusable profile.</td></tr>
<tr><td>Export configuration YAML…</td><td>The YAML used by the run.</td></tr>
</table>
<p>To compare runs, click <b>Compare</b>, select two or more runs of the same
workspace ({kbd("Ctrl")}+click, {kbd("Shift")}+click), then <b>Compare
selected</b>. See <a href="topic:comparison">Comparison</a>.</p>
""",
    ),
    HelpTopic(
        "comparison", "History and reports", "Comparison",
        "A verdict matrix across several historical runs.",
        "comparison compare matrix runs regression excel export verdict changed",
        f"""
<p><a href="page:comparison">Comparison</a> shows a matrix: one row per test,
one column per run, with the verdict of each run. It answers questions such as
<i>which tests regressed since yesterday?</i> or <i>is this reader worse than
the others?</i></p>
<ol class='steps'>
<li>In <a href="page:history">History</a>, click <b>Compare</b>.</li>
<li>Select two or more runs of the <b>same workspace</b>.</li>
<li>Click <b>Compare selected</b>.</li>
</ol>
<p>Use the search field to find a run, profile or workspace; remove a run from
the comparison with its chip. <b>Export Excel</b> saves the matrix as a
spreadsheet. If no verdict changed, the page says so.</p>
""",
    ),
    HelpTopic(
        "reports", "History and reports", "HTML reports",
        "Self-contained reports to share with people who do not have the tool.",
        "report html export share offline print mobile phone junit xml",
        f"""
<p>An HTML report is a <b>single file</b> that works offline, on a computer or a
phone, without Pytest Runner and without access to the project. It contains:</p>
<ul>
<li>the tree of the run or profile, with groups, colours and parametrized cases;</li>
<li>the verdict of each reader, the attempts, durations and tracebacks;</li>
<li>the archived logs and the effective YAML, with the origin of each value;</li>
<li>a print layout and a fallback view without JavaScript.</li>
</ul>
<p>Create it from <a href="page:history">History → Export → Export complete
HTML report…</a>. The report is generated in the background; when it is ready,
<b>Open report</b> opens it in the default browser. A run that is still being
saved must finish saving before its report can be exported.</p>
{tip("Send the HTML report rather than screenshots: the recipient can open every test, reader and log.")}
""",
    ),

    # =====================================================================
    # Application
    # =====================================================================
    HelpTopic(
        "settings", "Application", "Settings",
        "Every personal preference explained.",
        "settings preferences theme text size font compact atr bottom tree density row spacing tab duration follow timeouts collection interpreter discovery atr console notifications external editor vscode pycharm apply cancel",
        f"""
<p><a href="page:settings">Settings</a> are personal: they apply to your user
account on this workstation and never modify a workspace. Changes are
previewed immediately; <b>Apply settings</b> saves them and <b>Cancel
changes</b> returns to the saved values.</p>

<h2>Interface</h2>
<table>
<tr><th>Setting</th><th>Effect</th></tr>
<tr><td>Theme</td><td>Dark, light, and their colour-blind-friendly versions.</td></tr>
<tr><td>Text size</td><td>12 to 16 points, without changing the layout.</td></tr>
<tr><td>Compact top panels</td><td>Smaller margins in the three top panels.</td></tr>
<tr><td>ATR in the bottom bar</td><td>Shows the ATR in the status bar instead of next to the reader.</td></tr>
</table>

<h2>Tree &amp; details</h2>
<table>
<tr><th>Setting</th><th>Effect</th></tr>
<tr><td>Keep previous results in the test tree</td><td>Keeps the last known verdict of every test between runs.</td></tr>
<tr><td>Row spacing</td><td>Compact, Normal or Comfortable rows.</td></tr>
<tr><td>Tab when selecting another test</td><td><i>Last used</i> keeps the current tab, or always open a fixed tab.</td></tr>
<tr><td>Duration column</td><td>Shows or hides durations in the tree.</td></tr>
<tr><td>Follow the running test</td><td>Scrolls the tree to the executing test.</td></tr>
</table>

<h2>Timeouts (seconds)</h2>
<table>
<tr><th>Setting</th><th>Default</th></tr>
<tr><td>Test collection</td><td>120 s</td></tr>
<tr><td>Python interpreter check</td><td>15 s</td></tr>
<tr><td>Reader discovery</td><td>10 s</td></tr>
<tr><td>ATR monitor startup</td><td>10 s</td></tr>
</table>
<p>Increase them on slow workstations, network drives or very large suites.</p>

<h2>Console</h2>
<p>Choose which events the <a href="topic:console">Console</a> records
(interface actions, commands, process output, errors), timestamps, automatic
scrolling and how many events are kept in memory (250, 1,000 or 5,000).</p>

<h2>Notifications</h2>
<p><b>Notify when a run ends</b> shows a desktop notification, useful for long
runs.</p>

<h2>External editor</h2>
<p><b>Automatic</b> tries VS Code then PyCharm. Choose one, and optionally set
the path of its executable if it is not detected. {kbd("Ctrl")}+click on a
source link always opens the external editor.</p>
""",
    ),
    HelpTopic(
        "console", "Application", "Console",
        "The diagnostic journal of the session.",
        "console log journal diagnostic commands output errors traceback filter pause export copy clear support",
        f"""
<p>The <a href="page:console">Console</a> records what really happens during
the session: the exact commands started with their working directory, the
interface actions, the live pytest output of every reader, and the errors with
their tracebacks. It does not accept commands.</p>
<ul>
<li>Filters and search find an event.</li>
<li><b>Pause display</b> freezes the view while recording continues.</li>
<li><b>Copy</b> and <b>Export .log</b> use the filtered content.</li>
<li><b>Clear</b> empties the journal of the session.</li>
</ul>
{tip("When you report a problem, export the Console with Export .log and attach it, together with the support information of <a href='topic:support'>Support and data locations</a>.")}
<p>The Console is kept in memory only, for the current session.</p>
""",
    ),
    HelpTopic(
        "appearance", "Application", "Themes, accessibility and windows",
        "Themes, colour-blind palettes, text size, sidebar and detached windows.",
        "theme dark light colorblind colour blind accessibility contrast text size sidebar collapse small window detach window second screen",
        f"""
<h2>Themes</h2>
<p>The buttons at the bottom of the sidebar switch between <b>light</b> and
<b>dark</b>, and turn on the <b>colour-blind-friendly</b> palette. The same
choice is available in <a href="page:settings">Settings</a>. Verdicts use
colours <i>and</i> icons, so they stay recognizable without colour.</p>

<h2>Text size</h2>
<p><a href="topic:settings">Settings → Interface → Text size</a> enlarges the
text from 12 to 16 points.</p>

<h2>Sidebar and small windows</h2>
<p>The chevron at the bottom collapses the sidebar to icons; each icon keeps
its tooltip. Below 1,200 pixels of width the sidebar collapses automatically,
and the window can be reduced down to 800 × 560.</p>

<h2>Separate windows</h2>
<p><b>Detach window</b> on Settings and Console opens the page in its own
window, for example on a second screen; clicking it in the sidebar brings it
back to the front, and <b>Reattach to tab</b> puts it back. Run tabs and the
log comparison can be detached too. Positions are restored at the next
start.</p>
{tip("Keep this guide open in your browser next to the application while you learn it: F1 always brings you to the topic of the page you are on.")}
""",
    ),
    HelpTopic(
        "shortcuts", "Application", "Keyboard shortcuts",
        "Every keyboard shortcut in one table.",
        "shortcut shortcuts keyboard keys hotkey f1 f5 f6 f7 esc ctrl",
        f"""
<h2>Everywhere</h2>
<table>
<tr><th>Keys</th><th>Action</th></tr>
<tr><td>{kbd("F1")}</td><td>Help about the current page</td></tr>
<tr><td>{kbd("Ctrl", "O")}</td><td>Open a workspace</td></tr>
<tr><td>{kbd("Ctrl", "R")}</td><td>Collect the tests again</td></tr>
<tr><td>{kbd("F5")}</td><td>Run the selected tests (or add to the queue)</td></tr>
<tr><td>{kbd("F6")}</td><td>Re-run failed, errored and not-run tests</td></tr>
<tr><td>{kbd("Esc")}</td><td>Stop the run (ignored while typing in a field)</td></tr>
<tr><td>{kbd("Ctrl", "H")}</td><td>History</td></tr>
</table>

<h2>Test tree</h2>
<table>
<tr><th>Keys</th><th>Action</th></tr>
<tr><td>{kbd("Ctrl", "F")}</td><td>Find a test</td></tr>
<tr><td>{kbd("Ctrl", "M")}</td><td>Filter by marker</td></tr>
<tr><td>{kbd("Ctrl", "A")}</td><td>Select all</td></tr>
<tr><td>{kbd("Ctrl", "Shift", "A")}</td><td>Clear selection</td></tr>
<tr><td>{kbd("Ctrl", "D")}</td><td>Select tests where readers disagree</td></tr>
</table>

<h2>Result panel</h2>
<table>
<tr><th>Keys</th><th>Action</th></tr>
<tr><td>{kbd("Ctrl", "1")} … {kbd("Ctrl", "4")}</td><td>Detail, Source, Output, Logs</td></tr>
<tr><td>{kbd("Ctrl", "Shift", "D")}</td><td>Compare the logs of every reader</td></tr>
<tr><td>{kbd("F7")} / {kbd("Shift", "F7")}</td><td>Next / previous difference between readers</td></tr>
<tr><td>{kbd("Ctrl", "F")} in a log</td><td>Search in the log</td></tr>
<tr><td>{kbd("F3")} / {kbd("Shift", "F3")}</td><td>Next / previous match in the log</td></tr>
<tr><td>{kbd("Ctrl", "S")}</td><td>Save the file edited in Source</td></tr>
<tr><td>{kbd("Ctrl", "W")}</td><td>Close the log comparison window</td></tr>
</table>

<h2>Execution profiles</h2>
<table>
<tr><th>Keys</th><th>Action</th></tr>
<tr><td>{kbd("Ctrl", "C")} / {kbd("Ctrl", "V")}</td><td>Copy / paste after the selection</td></tr>
<tr><td>{kbd("Ctrl", "Shift", "V")}</td><td>Paste into the selected group</td></tr>
<tr><td>{kbd("Del")}</td><td>Remove the selection</td></tr>
<tr><td>{kbd("Ctrl", "Z")} / {kbd("Ctrl", "Y")}</td><td>Undo / redo</td></tr>
</table>
<p>In text fields, the usual editing shortcuts keep their normal behaviour.</p>
""",
    ),

    # =====================================================================
    # Troubleshooting
    # =====================================================================
    HelpTopic(
        "troubleshooting", "Troubleshooting", "Troubleshooting",
        "Common problems and how to solve them.",
        "problem error issue fix solve troubleshooting not working fails cannot no tests found file not found timeout readers missing slow",
        f"""
<table>
<tr><th>Symptom</th><th>Cause and solution</th></tr>
<tr><td><b>Python interpreter not usable</b> / banner on Run Tests</td>
<td>The test Python does not exist or has no pytest. Open
<a href="page:python">Python Environment</a>, select the right
<code>python.exe</code>, click <b>Test</b> then <b>Save</b>. Check also
<code>python_executable</code> in the YAML, which has priority.</td></tr>
<tr><td>The tree is empty after loading a workspace</td>
<td>Check that the folder contains <code>test_*.py</code> files and that the
interpreter works. Read the collection error, then the
<a href="page:console">Console</a> (category <i>Errors</i>).</td></tr>
<tr><td>Some files are red, <i>files could not be collected</i></td>
<td>Those files cannot be imported (syntax error, missing module). Select the
file to read the error in Detail, fix it, then {kbd("Ctrl", "R")}.</td></tr>
<tr><td><i>file or directory not found</i> when running</td>
<td>A test was renamed or deleted since the last collection, or the workspace
has no <code>pytest.ini</code> and the paths start from another folder. Collect
again with {kbd("Ctrl", "R")}.</td></tr>
<tr><td>Collection stops with a timeout</td>
<td>Large suite, network drive or slow antivirus. Increase <i>Test
collection</i> in <a href="topic:settings">Settings → Timeouts</a>.</td></tr>
<tr><td>A reader does not appear in the list</td>
<td>Plug it in, then open the list again (discovery restarts). Check the
driver. You can always type the reader name manually. Increase <i>Reader
discovery</i> if discovery times out.</td></tr>
<tr><td>No ATR</td>
<td>Insert a card and click the refresh icon of the ATR field. The ATR is not
read during a run.</td></tr>
<tr><td>Logs tab is empty</td>
<td>The tests write no <code>.log</code> file, or <code>log_directory</code>
points elsewhere. Check the key in <a href="topic:yaml-config">YAML
configuration</a>.</td></tr>
<tr><td>Tests marked <b>Not run</b></td>
<td>The run was stopped, a process crashed, or the tests were deactivated.
Read the reason in Detail. See <a href="topic:native-crash">Crashes and tests
not run</a>.</td></tr>
<tr><td>Run marked <b>Incomplete</b></td>
<td>Some files were not collected, or part of the campaign did not run. Click
<b>files not collected</b> to see why.</td></tr>
<tr><td><b>Run tests</b> says <b>Add to queue</b></td>
<td>Another tab is running. The run will start when it ends. See
<a href="topic:run-tabs">Run tabs and queue</a>.</td></tr>
<tr><td>{kbd("Esc")} does not stop the run</td>
<td>The cursor is in a text field. Click the tree, or use the <b>Stop</b>
button.</td></tr>
<tr><td>A profile cannot run</td>
<td>It contains a deactivated test, or tests that no longer exist. Check the
⊘ button and collect again.</td></tr>
<tr><td>Ctrl+click does not open my editor</td>
<td>Set the editor and its executable in <a href="topic:settings">Settings →
External editor</a>.</td></tr>
</table>
<p>Still stuck? See <a href="topic:support">Support and data locations</a>.</p>
""",
    ),
    HelpTopic(
        "faq", "Troubleshooting", "Frequently asked questions",
        "Short answers to common questions.",
        "faq question questions answer why how can i",
        f"""
<h3>Does Pytest Runner modify my tests or my YAML?</h3>
<p>No. Each run works on its own copy of the YAML, the reader is injected
without writing to disk, and deactivations are stored in the application data.
Only <b>Source</b> edits that you save, and YAML files you save explicitly,
change files.</p>

<h3>Can I close the application during a run?</h3>
<p>Closing stops the running pytest processes. Finished runs are already in
History. Paused runs need the application to stay open.</p>

<h3>Why do the application and the tests use different Pythons?</h3>
<p>So that the tests can use the exact environment they need (32-bit, specific
libraries) without depending on the application. See
<a href="topic:python-env">Python Environment</a>.</p>

<h3>Can I run tests with pytest-xdist?</h3>
<p>Yes, if <code>pytest-xdist</code> is installed in the test interpreter.
Live progress works with xdist.</p>

<h3>How do I share results with someone who does not have the tool?</h3>
<p>Export a complete HTML report from History. See
<a href="topic:reports">HTML reports</a>.</p>

<h3>How do I run the same suite on several configurations?</h3>
<p>Create an execution profile, duplicate the group of tests and give each copy
its own YAML parameters. See <a href="topic:profile-yaml">Per-test YAML
parameters</a>.</p>

<h3>Where are my profiles and my history?</h3>
<p>In your user folder. See <a href="topic:support">Support and data
locations</a>.</p>

<h3>Are my settings shared with my colleagues?</h3>
<p>No. Settings, history and deactivations belong to your user account on this
workstation. Share profiles with <b>Export</b> / <b>Import</b>, and results with
HTML reports.</p>
""",
    ),
    HelpTopic(
        "support", "Troubleshooting", "Support and data locations",
        "Version, environment, where data is stored and how to report a problem.",
        "support version about data location folder history profiles settings bug report contact copy support information",
        """
<h2>This installation</h2>
<table>
<tr><th>Item</th><th>Value</th></tr>
<tr><td>Pytest Runner</td><td>{version}</td></tr>
<tr><td>Application Python</td><td>{python}</td></tr>
<tr><td>Qt / PySide6</td><td>{qt}</td></tr>
<tr><td>Operating system</td><td>{os}</td></tr>
<tr><td>Test interpreter</td><td>{interpreter}</td></tr>
</table>

<h2>Where data is stored</h2>
<table>
<tr><th>Data</th><th>Location</th></tr>
<tr><td>Run history and archived logs</td><td><code>{history_dir}</code></td></tr>
<tr><td>Execution profiles and application data</td><td><code>{data_dir}</code></td></tr>
<tr><td>Personal settings</td><td><code>{settings_file}</code></td></tr>
</table>
<p>Back up the history and data folders to keep your runs and profiles when
changing workstation.</p>

<h2>Reporting a problem</h2>
<ol class='steps'>
<li>Click <b>Copy support information</b> above.</li>
<li>Open the <a href="page:console">Console</a> and click <b>Export .log</b>.</li>
<li>If the problem concerns a run, export its HTML report from
<a href="page:history">History</a>.</li>
<li>Describe what you did, what you expected and what happened, and attach
the files above.</li>
</ol>
""",
    ),
    HelpTopic(
        "glossary", "Troubleshooting", "Glossary",
        "The words used in the application.",
        "glossary definition term terms word meaning nodeid workspace collection fixture marker",
        """
<table>
<tr><th>Term</th><th>Meaning</th></tr>
<tr><td>ATR</td><td>Answer To Reset: the identification bytes returned by a smart card when it is powered.</td></tr>
<tr><td>Collection</td><td>The step where pytest finds the tests of the workspace, without running them.</td></tr>
<tr><td>Draft</td><td>A run tab that has not been started.</td></tr>
<tr><td>Fixture</td><td>pytest code that prepares (setup) and cleans (teardown) around a test. A failure there gives <b>Error</b>.</td></tr>
<tr><td>Marker</td><td>A pytest label on a test (<code>@pytest.mark.smoke</code>), usable to filter.</td></tr>
<tr><td>Nodeid</td><td>The unique pytest identifier of a test, such as <code>tests/test_api.py::test_login[admin]</code>.</td></tr>
<tr><td>Occurrence</td><td>One appearance of a test in a profile. The same test can appear several times.</td></tr>
<tr><td>Parametrized case</td><td>One set of parameters of a <code>@pytest.mark.parametrize</code> test, shown between brackets.</td></tr>
<tr><td>Primary reader</td><td>The reader written in the <code>Reader</code> key, run first.</td></tr>
<tr><td>Profile</td><td>A saved, ordered sequence of tests with groups and YAML parameters.</td></tr>
<tr><td>Queue</td><td>Runs waiting for the current run to finish.</td></tr>
<tr><td>Workspace</td><td>The folder that contains the tests and their configuration.</td></tr>
</table>
""",
    ),
]

TOPICS: tuple[HelpTopic, ...] = tuple(_TOPICS)
TOPICS_BY_ID = {topic.id: topic for topic in TOPICS}

# Rubrique ouverte par F1 selon la page affichee : l'aide contextuelle evite
# de chercher dans tout le guide la page qu'on a sous les yeux.
CONTEXT_TOPICS = {
    "workspace": "run-tests",
    "profiles": "profiles",
    "yaml": "yaml-config",
    "history": "history",
    "comparison": "comparison",
    "python": "python-env",
    "console": "console",
    "settings": "settings",
    "help": "welcome",
}

APP_PAGES = ("workspace", "profiles", "yaml", "history", "comparison",
             "python", "console", "settings")
