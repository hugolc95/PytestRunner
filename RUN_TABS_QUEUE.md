# Run tabs and queue

The Run Tests page keeps its existing tree and result panels inside independent
tabs. Use **+ New run** to prepare a selection while another tab displays live
results. Each new tab starts with an unchecked copy of the collected tests.
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
runs. The selected tab's result counters sit below the tabs and can filter its
tree. When viewing another tab, **Live** returns to the current execution.

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
