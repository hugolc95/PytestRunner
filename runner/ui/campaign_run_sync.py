"""Recharge une campagne sans deplacer les selections ou attribuer de vieux verdicts."""
import copy
from collections import defaultdict, deque

from PySide6.QtCore import QObject, QModelIndex, QTimer

from runner.domain.campaign_sync import compare, location_matches
from runner.domain.execution_profile import effective_step_overrides, group_path


class RunCampaignSync(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.pending = None
        window.campaign_notice.review.connect(self.review)
        window.campaign_notice.undo.connect(self.undo)
        window.campaign_notice.tracking.connect(self.sources)
        window.profiles_page.campaign_updated.connect(self.updated)
        window.service.finished.connect(self._finished)

    def refresh(self):
        w = self.window
        profile = w._active_execution_profile
        if profile is None or not w.profile_tree_button.isChecked():
            w.campaign_notice.hide()
            return
        plan = compare(profile, w.model._by_nodeid, w.workspace.path if w.workspace else '',
                       complete=getattr(w, '_campaign_collection_complete', bool(w.model._by_nodeid)))
        if not plan.problem:
            unavailable = set(plan.missing)
            missing = {key for key, (position, _, _) in w.profile_model.locations.items()
                       if position % len(profile.sequence) in unavailable}
            if w.profile_model.campaign_missing != missing:
                w.profile_model.set_campaign_missing(missing)
        w.campaign_notice.show_plan(plan, can_undo=profile.profile_id in w.profiles_page.campaign_sync.undo_updates)

    def review(self, profile=None):
        w = self.window
        profile = profile or w._active_execution_profile
        w.profiles_page.set_workspace_context(list(w.model._by_nodeid), w.workspace.config_path if w.workspace else '',
            workspace=w.workspace.path if w.workspace else '',
            complete=getattr(w, '_campaign_collection_complete', bool(w.model._by_nodeid)))
        w.profiles_page.campaign_sync.review(profile)
        self.refresh()

    def undo(self):
        profile = self.window._active_execution_profile
        if profile:
            self.window.profiles_page.campaign_sync.undo(profile.profile_id)

    def sources(self):
        w = self.window
        profile = w._active_execution_profile
        w._show_page('profiles')
        page = w.profiles_page
        if page._dirty:
            page._show_notice('Save or undo the current editor changes before choosing another campaign.', warning=True)
            return
        for row, candidate in enumerate(page._profiles):
            if profile and candidate.profile_id == profile.profile_id:
                page.profile_list.setCurrentRow(row)
                break
        page.manage_campaign_sources()

    def _finished(self, *_):
        # RunTabs libere son verrou dans un autre slot du meme signal.
        QTimer.singleShot(0, self._apply_pending)

    def _apply_pending(self):
        if self.pending:
            profile, previous = self.pending
            self.pending = None
            self.updated(profile, previous)

    def _branches(self):
        w = self.window
        model = w.profile_model
        def visit(parent=QModelIndex(), path=()):
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                node = index.internalPointer().node
                group = model._named_groups.get(id(node))
                key = path + ((node.kind.value, group['id'] if group else node.name),)
                if model.rowCount(index):
                    yield index, key
                    yield from visit(index, key)
        return list(visit())

    def updated(self, profile, previous):
        w = self.window
        active = w._active_execution_profile
        if active is None or active.profile_id != profile.profile_id:
            w._refresh_profile_picker()
            return
        if w.service.busy or w.run_tabs and w.run_tabs.is_locked(w):
            self.pending = (copy.deepcopy(profile), copy.deepcopy(previous))
            return
        if active == profile:
            self.refresh()
            return
        model, tree = w.profile_model, w.profile_tree
        expanded = {key: tree.isExpanded(index) for index, key in self._branches()}
        scroll = tree.verticalScrollBar().value(), tree.horizontalScrollBar().value()
        old_ids = active.step_ids
        if not old_ids and previous and previous.sequence == active.sequence:
            old_ids = previous.step_ids
        if not old_ids:
            # Les anciens profils n'avaient pas d'identites ; apparier les
            # occurrences identiques dans l'ordre, jamais un verdict homonyme.
            pools = defaultdict(deque)
            for identifier, nodeid in zip(profile.step_ids, profile.sequence):
                pools[nodeid].append(identifier)
            old_ids = [pools[n].popleft() if pools[n] else '' for n in active.sequence]
        new_positions = {identifier: i for i, identifier in enumerate(profile.step_ids)}
        checked_ids = set()
        checked_keys = {key for key, row in model._by_nodeid.items() if row.checked and row not in model._blocked_rows}
        previous_page = w.pages.currentWidget()
        all_old_ids = set()
        mapping = {}
        old_patches = effective_step_overrides(active) or [{} for _ in active.sequence]
        new_patches = effective_step_overrides(profile) or [{} for _ in profile.sequence]
        moved = location_matches(active.sequence, profile.sequence)
        for old_pos, identifier in enumerate(old_ids):
            all_old_ids.add(identifier)
            target = new_positions.get(identifier)
            for repeat in range(active.execution.repetitions):
                position = repeat * len(active.sequence) + old_pos
                if model.key(position) in checked_keys:
                    checked_ids.add((repeat, identifier))
                if target is not None and repeat < profile.execution.repetitions:
                    unchanged = ((active.sequence[old_pos] == profile.sequence[target] or moved.get(old_pos) == profile.sequence[target])
                                 and old_patches[old_pos] == new_patches[target]
                                 and active.configuration_text == profile.configuration_text)
                    for key in model.occurrence_keys(position):
                        if unchanged:
                            attempt = model.locations[key][1]
                            mapping[key] = model.key(repeat * len(profile.sequence) + target, attempt)
        statuses = [(mapping[key], dict(model._by_nodeid[key].statuses)) for key in mapping]
        durations = {mapping[key]: dict(values) for key, values in model._durations.items() if key in mapping}
        reports = {(mapping[key], r): value for (key, r), value in w._profile_reports.items() if key in mapping}
        details = {(mapping[key], r): value for (key, r), value in w._profile_live_details.items() if key in mapping}
        logs = copy.copy(w._profile_logs)
        if logs:
            logs.paths = {(mapping[key], r): path for (key, r), path in logs.paths.items() if key in mapping}
        current_index = tree.currentIndex()
        current_key = current_index.internalPointer().node.nodeid if current_index.isValid() else ''
        chosen_key = mapping.get(current_key)
        if chosen_key is None and current_key in model.locations:
            position = model.locations[current_key][0]
            target = new_positions.get(old_ids[position % len(active.sequence)])
            if target is not None:
                chosen_key = model.key((position // len(active.sequence)) * len(profile.sequence) + target)
        selected_branch = next((key for index, key in self._branches() if index == current_index), None)
        old_visible = w.profile_tree_button.isChecked()
        tree.setUpdatesEnabled(False)
        try:
            w._open_collected_profile(profile)
            for key, values in statuses:
                position, attempt = map(int, key.split(':'))
                nodeid = profile.sequence[position % len(profile.sequence)]
                for reader, status in values.items():
                    model.apply_execution(position, attempt, reader, nodeid, status)
            for key, values in durations.items():
                for reader, seconds in values.items():
                    model.set_duration(key, reader, seconds)
            w._profile_reports, w._profile_live_details, w._profile_logs = reports, details, logs
            selected = [model.key(repeat * len(profile.sequence) + position)
                for repeat in range(profile.execution.repetitions)
                for position, identifier in enumerate(profile.step_ids)
                if identifier not in all_old_ids or (repeat, identifier) in checked_ids]
            model.set_checked_nodeids(selected)
            for index, key in self._branches():
                if key in expanded:
                    tree.setExpanded(index, expanded[key])
                if key == selected_branch:
                    tree.setCurrentIndex(index)
            if chosen_key:
                tree.setCurrentIndex(model.index_for_nodeid(chosen_key))
            tree.verticalScrollBar().setValue(scroll[0])
            tree.horizontalScrollBar().setValue(scroll[1])
            if not old_visible:
                w._set_profile_tree_visible(False)
        finally:
            tree.setUpdatesEnabled(True)
        if previous_page is w.profiles_page and w._run_host is None:
            w._show_page('profiles')
        if w.run_tabs:
            w.run_tabs.schedule_save()
        self.refresh()
