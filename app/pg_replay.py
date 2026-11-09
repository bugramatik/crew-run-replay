import streamlit as st
from streamlit import session_state as ss

import db_utils
from i18n import t
from run_replay import (
    build_replay,
    changed_steps,
    diff_runs,
    diff_summary,
)


class PageReplay:
    def __init__(self):
        self.name = t("page.replay")

    def load_runs(self):
        if "results" not in ss or ss.results is None:
            ss.results = db_utils.load_results()
        return [build_replay(result) for result in ss.results]

    def draw_run_picker(self, runs):
        labels = {run.run_id: run.label for run in runs}
        return st.selectbox(
            t("replay.select_run"),
            options=[run.run_id for run in runs],
            format_func=lambda run_id: labels.get(run_id, run_id),
            key="replay_run_id",
        )

    def draw_steps(self, run):
        st.markdown(f"**{t('replay.steps')}:** {len(run.steps)}")
        if run.inputs:
            with st.expander(t("replay.inputs"), expanded=False):
                for name, value in run.inputs.items():
                    st.markdown(f"**{name}:** {value}")
        for position, step in enumerate(run.steps, 1):
            with st.container(border=True):
                st.markdown(f"**{position}. {step.title}**")
                st.code(step.output or t("replay.empty_output"), language=None)
        if run.final_output:
            with st.expander(t("replay.final_output"), expanded=False):
                st.write(run.final_output)

    def draw_compare(self, runs):
        labels = {run.run_id: run.label for run in runs}
        col1, col2 = st.columns(2)
        with col1:
            left_id = st.selectbox(
                t("replay.left_run"),
                options=[run.run_id for run in runs],
                index=1 if len(runs) > 1 else 0,
                format_func=lambda run_id: labels.get(run_id, run_id),
                key="replay_left_id",
            )
        with col2:
            right_id = st.selectbox(
                t("replay.right_run"),
                options=[run.run_id for run in runs],
                index=0,
                format_func=lambda run_id: labels.get(run_id, run_id),
                key="replay_right_id",
            )

        by_id = {run.run_id: run for run in runs}
        left = by_id[left_id]
        right = by_id[right_id]
        diff_lines = diff_runs(left, right)
        summary = diff_summary(diff_lines)

        col1, col2, col3 = st.columns(3)
        col1.metric(t("replay.added_lines"), summary["added"])
        col2.metric(t("replay.removed_lines"), summary["removed"])
        col3.metric(t("replay.changed_steps"), len(changed_steps(left, right)))

        if not diff_lines:
            st.info(t("replay.no_differences"))
            return
        st.code("\n".join(diff_lines), language="diff")

    def draw(self):
        st.subheader(self.name)
        runs = self.load_runs()
        if not runs:
            st.write(t("replay.no_results"))
            return

        mode = st.radio(
            t("replay.mode"),
            options=["steps", "compare"],
            format_func=lambda value: t(f"replay.mode_{value}"),
            horizontal=True,
            key="replay_mode",
        )

        if mode == "steps":
            run_id = self.draw_run_picker(runs)
            run = next(run for run in runs if run.run_id == run_id)
            self.draw_steps(run)
        else:
            if len(runs) < 2:
                st.write(t("replay.need_two_runs"))
                return
            self.draw_compare(runs)
