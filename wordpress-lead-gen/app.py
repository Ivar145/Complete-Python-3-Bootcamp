import json

import streamlit as st

from database import (
    add_email_log,
    add_lead,
    auto_flag_followups,
    delete_lead,
    delete_template,
    get_all_settings,
    get_categories,
    get_email_log,
    get_lead,
    get_leads,
    get_project,
    get_projects,
    get_setting,
    get_template,
    get_templates,
    init_db,
    mark_replies_received,
    save_project,
    save_setting,
    save_template,
    update_lead,
)
from email_handler import check_all_replies, check_for_reply, send_email
from lead_finder import find_leads
from seo_checker import check_seo

st.set_page_config(page_title="WP Lead Finder", layout="wide")
init_db()


def render_template(body: str, subject: str, lead: dict, your_name: str) -> tuple[str, str]:
    issues = json.loads(lead.get("seo_issues") or "[]")
    vals = {
        "business_name": lead.get("name", ""),
        "owner_name": lead.get("contact_name") or lead.get("name", ""),
        "city": lead.get("location", ""),
        "issue": issues[0] if issues else ("no website" if lead.get("priority") == 1 else "SEO issues"),
        "category": lead.get("category", ""),
        "your_name": your_name,
    }

    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    return subject.format_map(SafeDict(vals)), body.format_map(SafeDict(vals))


STATUS_LABELS = {
    "new": "🟦 New",
    "contacted": "🟨 Contacted",
    "follow_up": "🟧 Follow-up",
    "replied": "🟩 Replied",
    "booked": "✅ Booked",
    "cold": "🔘 Cold",
}

STATUS_OPTIONS = ["new", "contacted", "follow_up", "replied", "booked", "cold"]


tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Lead Finder", "Outreach Tracker", "Templates", "Projects", "Settings"]
)


# ──────────────────────────────────────────────
# Tab 1: Lead Finder
# ──────────────────────────────────────────────
with tab1:
    st.header("Lead Finder")

    api_key_default = get_setting("google_places_api_key")

    col1, col2 = st.columns(2)
    with col1:
        location = st.text_input("Location", placeholder="e.g. Chicago, IL")
        category = st.text_input("Business Category", placeholder="e.g. barber, dentist")
    with col2:
        max_results = st.slider("Max businesses to check", 20, 200, 60, step=10)
        api_key = st.text_input("Google Places API Key", value=api_key_default, type="password")

    if st.button("Find Leads", type="primary", use_container_width=True):
        if not location or not category:
            st.error("Please enter both a location and a category.")
        elif not api_key:
            st.error("Please enter a Google Places API key (or save it in Settings).")
        else:
            progress_bar = st.progress(0)
            status_placeholder = st.empty()

            def progress_cb(message: str, current: int, total: int):
                if total > 0:
                    progress_bar.progress(min(current / total, 1.0))
                status_placeholder.text(message)

            with st.spinner("Searching Google Places..."):
                raw_leads = find_leads(
                    location=location,
                    category=category,
                    api_key=api_key,
                    max_results=max_results,
                    include_with_website=True,
                    progress_callback=progress_cb,
                )

            progress_bar.empty()
            status_placeholder.empty()

            priority1 = []
            priority2 = []

            seo_threshold = int(get_setting("seo_threshold") or 70)
            seo_progress = st.progress(0)
            seo_status = st.empty()
            with_website = [l for l in raw_leads if l.get("website")]
            passed_seo = []
            blocked_seo = []

            for i, lead in enumerate(with_website):
                seo_status.text(f"Checking SEO: {lead['name']} ({i + 1}/{len(with_website)})")
                seo_progress.progress((i + 1) / max(len(with_website), 1))
                result = check_seo(lead["website"])
                lead["seo_score"] = result["score"]
                lead["seo_issues"] = json.dumps(result["issues"])
                lead["priority"] = 2
                if result.get("blocked"):
                    blocked_seo.append(lead)
                elif result["score"] < seo_threshold:
                    priority2.append(lead)
                else:
                    passed_seo.append(lead)

            seo_progress.empty()
            seo_status.empty()
            st.session_state["finder_passed"] = passed_seo
            st.session_state["finder_blocked"] = blocked_seo

            for lead in raw_leads:
                if not lead.get("website"):
                    lead["priority"] = 1
                    lead["seo_score"] = None
                    lead["seo_issues"] = json.dumps([])
                    priority1.append(lead)

            st.session_state["finder_p1"] = priority1
            st.session_state["finder_p2"] = priority2
            st.session_state["added_p1"] = set()
            st.session_state["added_p2"] = set()
            st.session_state["added_passed"] = set()
            st.session_state["added_blocked"] = set()
            st.success(
                f"Done! Found {len(priority1)} businesses with no website and {len(priority2)} with poor SEO."
            )

    if "finder_p1" in st.session_state or "finder_p2" in st.session_state:
        priority1 = st.session_state.get("finder_p1", [])
        priority2 = st.session_state.get("finder_p2", [])
        passed_seo = st.session_state.get("finder_passed", [])
        blocked_seo = st.session_state.get("finder_blocked", [])

        def add_all(leads_list):
            count = 0
            for lead in leads_list:
                result = add_lead(lead)
                count += 1
            st.success(f"Added {count} leads to tracker.")

        with st.expander(f"Priority 1 — No Website ({len(priority1)} found)", expanded=True):
            if not priority1:
                st.info("No businesses found without a website.")
            else:
                if st.button("Add All to Tracker", key="add_all_p1"):
                    add_all(priority1)
                    st.session_state["added_p1"] = set(range(len(priority1)))
                    st.rerun()

                added_p1 = st.session_state.get("added_p1", set())
                for i, lead in enumerate(priority1):
                    c1, c2 = st.columns([4, 1])
                    if i in added_p1:
                        with c1:
                            st.markdown(f"~~{lead['name']}~~")
                            st.caption(f"{lead.get('address', '')} · {lead.get('phone', '') or 'No phone'}")
                        with c2:
                            st.markdown("✅ Added")
                    else:
                        with c1:
                            st.markdown(f"**{lead['name']}**")
                            st.caption(f"{lead.get('address', '')} · {lead.get('phone', '') or 'No phone'}")
                        with c2:
                            if st.button("Add to Tracker", key=f"add_p1_{i}"):
                                add_lead(lead)
                                added_p1.add(i)
                                st.session_state["added_p1"] = added_p1
                                st.rerun()
                    st.divider()

        with st.expander(f"Priority 2 — Poor SEO ({len(priority2)} found)", expanded=True):
            if not priority2:
                st.info("No businesses found with poor SEO.")
            else:
                if st.button("Add All to Tracker", key="add_all_p2"):
                    add_all(priority2)
                    st.session_state["added_p2"] = set(range(len(priority2)))
                    st.rerun()

                added_p2 = st.session_state.get("added_p2", set())
                for i, lead in enumerate(priority2):
                    c1, c2 = st.columns([4, 1])
                    if i in added_p2:
                        with c1:
                            st.markdown(f"~~{lead['name']}~~ — SEO Score: {lead.get('seo_score', 'N/A')}")
                            st.caption(f"{lead.get('address', '')} · {lead.get('phone', '') or 'No phone'}")
                        with c2:
                            st.markdown("✅ Added")
                    else:
                        with c1:
                            st.markdown(f"**{lead['name']}** — SEO Score: {lead.get('seo_score', 'N/A')}")
                            st.caption(f"{lead.get('address', '')} · {lead.get('phone', '') or 'No phone'}")
                            issues = json.loads(lead.get("seo_issues") or "[]")
                            if issues:
                                for issue in issues:
                                    st.caption(f"⚠ {issue}")
                        with c2:
                            if st.button("Add to Tracker", key=f"add_p2_{i}"):
                                add_lead(lead)
                                added_p2.add(i)
                                st.session_state["added_p2"] = added_p2
                                st.rerun()
                    st.divider()

        seo_threshold = int(get_setting("seo_threshold") or 70)
        with st.expander(f"Passed SEO — score ≥ {seo_threshold} ({len(passed_seo)} found)", expanded=False):
            if not passed_seo:
                st.info("No businesses passed the SEO threshold.")
            else:
                st.caption("These sites passed the automated check. Add manually if you know their SEO is poor.")
                if st.button("Add All to Tracker", key="add_all_passed"):
                    for lead in passed_seo:
                        add_lead(lead)
                    st.session_state["added_passed"] = set(range(len(passed_seo)))
                    st.rerun()

                added_passed = st.session_state.get("added_passed", set())
                for i, lead in enumerate(passed_seo):
                    c1, c2 = st.columns([4, 1])
                    if i in added_passed:
                        with c1:
                            st.markdown(f"~~{lead['name']}~~ — SEO Score: {lead.get('seo_score', 'N/A')}")
                            st.caption(f"{lead.get('address', '')} · {lead.get('phone', '') or 'No phone'}")
                        with c2:
                            st.markdown("✅ Added")
                    else:
                        with c1:
                            st.markdown(f"**{lead['name']}** — SEO Score: {lead.get('seo_score', 'N/A')}")
                            st.caption(f"{lead.get('address', '')} · {lead.get('website', '')}")
                            issues = json.loads(lead.get("seo_issues") or "[]")
                            for issue in issues:
                                st.caption(f"⚠ {issue}")
                        with c2:
                            if st.button("Add to Tracker", key=f"add_passed_{i}"):
                                add_lead(lead)
                                added_passed.add(i)
                                st.session_state["added_passed"] = added_passed
                                st.rerun()
                    st.divider()

        with st.expander(f"⚠ Could Not Check SEO ({len(blocked_seo)} found)", expanded=False):
            if not blocked_seo:
                st.info("All sites with websites were reachable.")
            else:
                st.caption("These sites blocked the SEO checker. Review them manually — blocking scrapers can itself be a sign of poor technical setup.")
                if st.button("Add All to Tracker", key="add_all_blocked"):
                    for lead in blocked_seo:
                        add_lead(lead)
                    st.session_state["added_blocked"] = set(range(len(blocked_seo)))
                    st.rerun()

                added_blocked = st.session_state.get("added_blocked", set())
                for i, lead in enumerate(blocked_seo):
                    c1, c2 = st.columns([4, 1])
                    if i in added_blocked:
                        with c1:
                            st.markdown(f"~~{lead['name']}~~")
                            st.caption(lead.get("website", ""))
                        with c2:
                            st.markdown("✅ Added")
                    else:
                        with c1:
                            st.markdown(f"**{lead['name']}**")
                            st.caption(f"{lead.get('website', '')} · {lead.get('address', '')}")
                            issues = json.loads(lead.get("seo_issues") or "[]")
                            for issue in issues:
                                st.caption(f"⚠ {issue}")
                        with c2:
                            if st.button("Add to Tracker", key=f"add_blocked_{i}"):
                                add_lead(lead)
                                added_blocked.add(i)
                                st.session_state["added_blocked"] = added_blocked
                                st.rerun()
                    st.divider()


# ──────────────────────────────────────────────
# Tab 2: Outreach Tracker
# ──────────────────────────────────────────────
with tab2:
    if "followups_flagged" not in st.session_state:
        follow_up_days = int(get_setting("follow_up_days") or 14)
        auto_flag_followups(follow_up_days)
        st.session_state["followups_flagged"] = True

    st.header("Outreach Tracker")

    left, right = st.columns([1, 2])

    with left:
        search_query = st.text_input("Search leads", placeholder="Name or address...")
        status_filter = st.selectbox(
            "Status",
            ["All", "New", "Contacted", "Follow-up", "Replied", "Booked", "Cold"],
        )
        priority_filter = st.selectbox(
            "Priority", ["All", "P1 - No Website", "P2 - Poor SEO"]
        )
        categories = get_categories()
        category_filter = st.selectbox("Category", ["All"] + categories)

        status_map = {
            "All": None,
            "New": "new",
            "Contacted": "contacted",
            "Follow-up": "follow_up",
            "Replied": "replied",
            "Booked": "booked",
            "Cold": "cold",
        }
        priority_map = {"All": None, "P1 - No Website": 1, "P2 - Poor SEO": 2}

        leads = get_leads(
            status=status_map[status_filter],
            priority=priority_map[priority_filter],
            category=None if category_filter == "All" else category_filter,
            search=search_query or None,
        )

        st.markdown(f"**{len(leads)} leads**")
        for lead in leads:
            label = STATUS_LABELS.get(lead["status"], lead["status"])
            priority_icon = "🔴" if lead["priority"] == 1 else "🟡"
            cat = f"[{lead['category']}]  " if lead.get("category") else ""
            btn_label = f"{priority_icon} {lead['name']}  {cat}{label}"
            if st.button(btn_label, key=f"lead_btn_{lead['id']}", use_container_width=True):
                st.session_state["selected_lead_id"] = lead["id"]
                st.session_state.pop("confirm_delete", None)

    with right:
        selected_id = st.session_state.get("selected_lead_id")
        if not selected_id:
            st.info("Select a lead from the list to view details.")
        else:
            lead = get_lead(selected_id)
            if not lead:
                st.warning("Lead not found.")
            else:
                priority_badge = "🔴 P1 – No Website" if lead["priority"] == 1 else "🟡 P2 – Poor SEO"
                st.subheader(f"{lead['name']}  {priority_badge}")

                if lead.get("google_maps_url"):
                    st.markdown(f"[View on Google Maps]({lead['google_maps_url']})")

                with st.form("lead_detail_form"):
                    contact_name = st.text_input("Contact Name", value=lead.get("contact_name") or "")
                    contact_email = st.text_input("Contact Email", value=lead.get("contact_email") or "")
                    contact_method = st.selectbox(
                        "Contact Method",
                        ["email", "phone", "both"],
                        index=["email", "phone", "both"].index(lead.get("contact_method") or "email"),
                    )
                    notes = st.text_area("Notes", value=lead.get("notes") or "")

                    current_status = lead.get("status") or "new"
                    status_idx = STATUS_OPTIONS.index(current_status) if current_status in STATUS_OPTIONS else 0
                    new_status = st.selectbox(
                        "Status",
                        STATUS_OPTIONS,
                        index=status_idx,
                        format_func=lambda s: STATUS_LABELS.get(s, s),
                    )

                    revenue = None
                    if new_status == "booked":
                        revenue = st.number_input(
                            "Revenue ($)",
                            value=float(lead.get("revenue") or 0),
                            min_value=0.0,
                            step=50.0,
                        )

                    if lead.get("priority") == 2:
                        issues = json.loads(lead.get("seo_issues") or "[]")
                        if issues:
                            st.markdown("**SEO Issues:**")
                            for issue in issues:
                                st.caption(f"⚠ {issue}")

                    save_btn = st.form_submit_button("Save Changes", type="primary")
                    if save_btn:
                        kwargs = dict(
                            contact_name=contact_name,
                            contact_email=contact_email,
                            contact_method=contact_method,
                            notes=notes,
                            status=new_status,
                        )
                        if new_status == "booked":
                            kwargs["revenue"] = revenue
                        update_lead(selected_id, **kwargs)
                        st.success("Saved!")
                        st.rerun()

                st.divider()
                st.subheader("Send Email")

                templates = get_templates()
                if not templates:
                    st.info("No templates found. Create one in the Templates tab.")
                else:
                    template_names = [t["name"] for t in templates]
                    selected_tmpl_idx = st.selectbox(
                        "Template", range(len(templates)), format_func=lambda i: template_names[i]
                    )
                    chosen_template = templates[selected_tmpl_idx]
                    your_name = get_setting("your_name")

                    rendered_subject, rendered_body = render_template(
                        chosen_template["body"],
                        chosen_template["subject"],
                        lead,
                        your_name,
                    )

                    email_subject = st.text_input("Subject", value=rendered_subject, key="email_subject")
                    email_body = st.text_area("Body", value=rendered_body, height=250, key="email_body")

                    send_col, reply_col = st.columns(2)
                    with send_col:
                        if st.button("Send Email", type="primary"):
                            gmail = get_setting("gmail_address")
                            pwd = get_setting("gmail_app_password")
                            to_addr = lead.get("contact_email", "")
                            if not to_addr:
                                st.error("No contact email set for this lead.")
                            elif not gmail or not pwd:
                                st.error("Configure Gmail credentials in Settings.")
                            else:
                                success, msg_id, err = send_email(gmail, pwd, to_addr, email_subject, email_body)
                                if success:
                                    add_email_log(selected_id, email_subject, email_body, msg_id)
                                    update_lead(
                                        selected_id,
                                        status="contacted",
                                        last_contacted_at=__import__("datetime").datetime.utcnow().isoformat(),
                                        email_thread_id=msg_id,
                                        follow_up_count=(lead.get("follow_up_count") or 0) + 1,
                                    )
                                    st.success(f"Email sent! Message ID: {msg_id}")
                                    st.rerun()
                                else:
                                    st.error(f"Failed to send: {err}")

                    with reply_col:
                        if st.button("Check for Reply"):
                            gmail = get_setting("gmail_address")
                            pwd = get_setting("gmail_app_password")
                            msg_id = lead.get("email_thread_id", "")
                            if not msg_id:
                                st.warning("No sent email recorded for this lead.")
                            elif not gmail or not pwd:
                                st.error("Configure Gmail credentials in Settings.")
                            else:
                                has_reply = check_for_reply(gmail, pwd, msg_id)
                                if has_reply:
                                    mark_replies_received([selected_id])
                                    st.success("Reply found! Status updated to Replied.")
                                    st.rerun()
                                else:
                                    st.info("No reply found yet.")

                with st.expander("Email History"):
                    logs = get_email_log(selected_id)
                    if not logs:
                        st.info("No emails sent yet.")
                    else:
                        for log in logs:
                            st.markdown(f"**{log['subject']}** — {log['sent_at']}")
                            st.text(log["body"][:300] + ("..." if len(log["body"]) > 300 else ""))
                            st.divider()

                st.divider()
                if st.session_state.get("confirm_delete") == selected_id:
                    st.warning("Are you sure you want to delete this lead? This cannot be undone.")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Yes, Delete", type="primary"):
                            delete_lead(selected_id)
                            st.session_state.pop("selected_lead_id", None)
                            st.session_state.pop("confirm_delete", None)
                            st.success("Lead deleted.")
                            st.rerun()
                    with c2:
                        if st.button("Cancel"):
                            st.session_state.pop("confirm_delete", None)
                            st.rerun()
                else:
                    if st.button("🗑 Delete Lead", type="secondary"):
                        st.session_state["confirm_delete"] = selected_id
                        st.rerun()


# ──────────────────────────────────────────────
# Tab 3: Templates
# ──────────────────────────────────────────────
with tab3:
    st.header("Email Templates")

    templates = get_templates()

    left_t, right_t = st.columns([1, 2])

    with left_t:
        if st.button("+ New Template", use_container_width=True):
            st.session_state["editing_template"] = None

        for tmpl in templates:
            if st.button(tmpl["name"], key=f"tmpl_btn_{tmpl['id']}", use_container_width=True):
                st.session_state["editing_template"] = tmpl["id"]

    with right_t:
        if "editing_template" not in st.session_state:
            st.info("Select a template to edit or create a new one.")
        else:
            editing_id = st.session_state["editing_template"]
            existing = get_template(editing_id) if editing_id else None

            st.subheader("Edit Template" if existing else "New Template")

            with st.form("template_form"):
                tmpl_name = st.text_input("Template Name", value=existing["name"] if existing else "")
                tmpl_subject = st.text_input("Subject", value=existing["subject"] if existing else "")
                tmpl_body = st.text_area(
                    "Body", value=existing["body"] if existing else "", height=300
                )

                st.caption(
                    "Available placeholders: `{business_name}` `{owner_name}` `{city}` `{issue}` `{category}` `{your_name}`"
                )

                save_col, del_col = st.columns(2)
                with save_col:
                    save_tmpl = st.form_submit_button("Save Template", type="primary")
                with del_col:
                    del_tmpl = st.form_submit_button("Delete Template") if existing else None

                if save_tmpl:
                    if not tmpl_name:
                        st.error("Template name is required.")
                    else:
                        save_template(tmpl_name, tmpl_subject, tmpl_body, template_id=editing_id)
                        st.success("Template saved!")
                        st.rerun()

                if del_tmpl and existing:
                    delete_template(editing_id)
                    st.session_state.pop("editing_template", None)
                    st.success("Template deleted.")
                    st.rerun()


# ──────────────────────────────────────────────
# Tab 4: Projects
# ──────────────────────────────────────────────
with tab4:
    st.header("Projects")

    from datetime import date, datetime

    booked_leads = get_leads(status="booked")

    if not booked_leads:
        st.info("No booked leads yet. Mark a lead as 'Booked' in the Outreach Tracker to add it here.")
    else:
        for lead in booked_leads:
            with st.expander(f"{lead['name']} — {lead.get('location', '')}", expanded=True):
                project = get_project(lead["id"])

                if project:
                    proj_status = project.get("status", "in_progress")
                    deadline_str = project.get("deadline", "")

                    if proj_status == "delivered":
                        st.success("✅ Delivered")
                    elif deadline_str:
                        try:
                            deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d").date()
                            days_left = (deadline_dt - date.today()).days
                            if days_left < 0:
                                st.error(f"⚠ Overdue by {abs(days_left)} days")
                            elif days_left < 3:
                                st.error(f"🔴 {days_left} days left")
                            elif days_left <= 7:
                                st.warning(f"🟠 {days_left} days left")
                            else:
                                st.success(f"🟢 {days_left} days left")
                        except ValueError:
                            pass

                with st.form(f"project_form_{lead['id']}"):
                    proj_name = st.text_input(
                        "Project Name",
                        value=project["name"] if project else f"{lead['name']} Website",
                    )
                    c1, c2 = st.columns(2)
                    with c1:
                        start_date = st.date_input(
                            "Start Date",
                            value=datetime.strptime(project["start_date"], "%Y-%m-%d").date()
                            if project and project.get("start_date")
                            else date.today(),
                        )
                    with c2:
                        deadline = st.date_input(
                            "Deadline",
                            value=datetime.strptime(project["deadline"], "%Y-%m-%d").date()
                            if project and project.get("deadline")
                            else date.today(),
                        )
                    proj_status_input = st.selectbox(
                        "Status",
                        ["in_progress", "delivered"],
                        index=0 if not project or project.get("status") == "in_progress" else 1,
                        format_func=lambda s: "In Progress" if s == "in_progress" else "Delivered",
                    )
                    proj_notes = st.text_area(
                        "Notes", value=project["notes"] if project and project.get("notes") else ""
                    )

                    if st.form_submit_button("Save Project", type="primary"):
                        save_project(
                            lead["id"],
                            proj_name,
                            str(start_date),
                            str(deadline),
                            proj_status_input,
                            proj_notes,
                        )
                        st.success("Project saved!")
                        st.rerun()


# ──────────────────────────────────────────────
# Tab 5: Settings
# ──────────────────────────────────────────────
with tab5:
    st.header("Settings")

    settings = get_all_settings()

    with st.form("settings_form"):
        your_name = st.text_input("Your Name", value=settings.get("your_name", ""))
        gmail_address = st.text_input("Gmail Address", value=settings.get("gmail_address", ""))
        gmail_app_password = st.text_input(
            "Gmail App Password",
            value=settings.get("gmail_app_password", ""),
            type="password",
        )
        google_places_api_key = st.text_input(
            "Google Places API Key",
            value=settings.get("google_places_api_key", ""),
            type="password",
        )
        follow_up_days = st.number_input(
            "Follow-up Days (days after contact before flagging)",
            value=int(settings.get("follow_up_days") or 14),
            min_value=1,
            max_value=90,
            step=1,
        )
        seo_threshold = st.number_input(
            "SEO Threshold — sites scoring below this are flagged as Poor SEO (0–100)",
            value=int(settings.get("seo_threshold") or 70),
            min_value=10,
            max_value=100,
            step=5,
        )

        if st.form_submit_button("Save Settings", type="primary"):
            save_setting("your_name", your_name)
            save_setting("gmail_address", gmail_address)
            save_setting("gmail_app_password", gmail_app_password)
            save_setting("google_places_api_key", google_places_api_key)
            save_setting("follow_up_days", str(int(follow_up_days)))
            save_setting("seo_threshold", str(int(seo_threshold)))
            st.success("Settings saved!")

    st.divider()

    col_test, col_replies = st.columns(2)

    with col_test:
        st.subheader("Test Gmail Connection")
        if st.button("Test Gmail Connection"):
            import smtplib

            g_addr = get_setting("gmail_address")
            g_pwd = get_setting("gmail_app_password")
            if not g_addr or not g_pwd:
                st.error("Gmail credentials not configured.")
            else:
                try:
                    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                        server.login(g_addr, g_pwd)
                    st.success("Gmail connection successful!")
                except smtplib.SMTPAuthenticationError:
                    st.error("Authentication failed — check your app password.")
                except Exception as e:
                    st.error(f"Connection failed: {e}")

    with col_replies:
        st.subheader("Check All Replies")
        if st.button("Check All Replies"):
            g_addr = get_setting("gmail_address")
            g_pwd = get_setting("gmail_app_password")
            if not g_addr or not g_pwd:
                st.error("Gmail credentials not configured.")
            else:
                contacted_leads = get_leads(status="contacted") + get_leads(status="follow_up")
                if not contacted_leads:
                    st.info("No contacted or follow-up leads to check.")
                else:
                    replied_ids = check_all_replies(g_addr, g_pwd, contacted_leads)
                    if replied_ids:
                        mark_replies_received(replied_ids)
                        st.success(f"Found {len(replied_ids)} new replies! Statuses updated.")
                    else:
                        st.info("No new replies found.")
