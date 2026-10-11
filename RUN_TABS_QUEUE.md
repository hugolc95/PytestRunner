# Run tabs and queue

The Run Tests page keeps its existing tree and result panels inside independent
tabs. Use **+ New run** to prepare a selection while another tab displays live
results. Each new tab starts with an unchecked copy of the collected tests.
The **+ New run** button follows the last tab; overflowing tabs remain scrollable.
Creating a draft shows **Preparing…** without opening temporary native windows.
Every tab receives the same personal preferences and diagnostics as the first
run: density, compact panels, default result view and automatic test following.
Its own status footer displays collection/run progress, elapsed time and ATR;
switching tabs or detaching moves that footer with the run. New drafts inherit
reader choices, recent environments and panel/column sizes, while test selections
and verdicts start clean. Panel/column sizes are also saved with each session.
Keyboard shortcuts work in attached and detached runs: **F5** starts the selected
run, **Ctrl+R** recollects tests, and **Esc** stops the active execution.
Execution profiles can also be loaded into a draft; opening a profile while the
selected tab is running or waiting creates a new draft automatically.

**Run tests / Run profile** starts immediately when execution is idle. During a
run, the button becomes **Add to queue**. Queued selections, reader choices,
environment, execution options and YAML configuration are captured when added.
Only one run executes at a time; the next starts after the previous run and its
report archiving finish. Results remain associated with their original tab.

Drag tabs to reorder waiting runs. The tab context menu can duplicate a run,
move it in the queue, remove it from the queue for editing, or close it.
**Pause queue** lets the current run finish and holds subsequent runs.
Stopping a run cancels that run; pause the queue to also prevent the next start.

The tab cards identify running work in blue, waiting work in amber, successful
work in green and failed work in red, with explicit text for every state.
Completed tabs show their overall verdict, including incomplete or stopped
runs. The selected tab keeps its original RESULTS panel with the progress ring
and clickable result counters. When viewing another tab, **Live** returns to
the current execution from the compact tab row.

The ENVIRONMENT panel places multiple-reader selection below Browse / Collect,
with the run name alongside those actions. EXECUTION contains the primary-reader
dropdown, ATR and a single row of run actions. Compact spacing keeps the tree
and detail pane higher on the page while preserving the result ring and counters.
Changing the workspace, configuration or interpreter resets a completed tab
to a clean draft; reports already saved in History are retained.

The tab context menu's **Detach tab** opens the same tree and results in a separate window. Closing
that window hides it; selecting its tab opens it again. **Reattach tab** brings
it back into the main window. The last selected attached tab remains visible
behind the detached window.

Draft selections, profiles, tab names and detached window geometry are restored
on application restart. Previous running and waiting tabs reopen as drafts;
restarting the application never silently starts an execution. Completed
reports remain available in History.

Reader discovery and ATR hardware polling are suspended during execution.
Source and shared configuration editing are disabled while a run is active.
