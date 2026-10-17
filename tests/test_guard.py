"""Tests for scripts/guard.py. Nothing reaches Basecamp: api_get is replaced by a fake board.

Run: python3 -m unittest discover -s tests
"""
import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("guard", os.path.join(ROOT, "scripts", "guard.py"))
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)

ACCOUNT = 1000001
ME, OTHER = 2001, 2002
TODO, BACKLOG = 301, 302
IN_PROGRESS, IN_REVIEW, DONE, CLOSING = 401, 402, 403, 404
BASE = f"https://3.basecampapi.com/{ACCOUNT}"
NOW = datetime.now(timezone.utc)


def person(person_id):
    return {"id": person_id, "name": f"person {person_id}"}


def card(card_id, column, assignees=(), creator=OTHER, age_minutes=600):
    created = (NOW - timedelta(minutes=age_minutes)).isoformat().replace("+00:00", "Z")
    return {"id": card_id, "parent": {"id": column}, "assignees": [person(p) for p in assignees],
            "creator": person(creator), "created_at": created}


CARDS = {
    10: card(10, TODO),                          # unassigned, normal column
    11: card(11, BACKLOG),                       # unassigned, another normal column
    12: card(12, IN_PROGRESS),
    13: card(13, IN_REVIEW),
    14: card(14, DONE),
    15: card(15, CLOSING),
    16: card(16, TODO, assignees=[OTHER]),
    20: card(20, TODO, assignees=[ME]),
    21: card(21, IN_REVIEW, assignees=[ME, OTHER]),
    30: card(30, TODO, creator=ME, age_minutes=5),      # mine, unassigned, just created
    31: card(31, TODO, creator=ME, age_minutes=600),    # mine, unassigned, old
    32: card(32, IN_PROGRESS, creator=ME, age_minutes=5),
}
STEPS = {500: {"id": 500, "parent": {"id": 20}}, 501: {"id": 501, "parent": {"id": 16}}}


def fake_api_get(config, path):
    kind, _, rest = path.rpartition("/")
    item_id = int(rest.split(".")[0])
    table = CARDS if kind == "/card_tables/cards" else STEPS if kind == "/card_tables/steps" else {}
    if item_id not in table:
        raise OSError("404 Not Found")
    return table[item_id]


guard.api_get = fake_api_get


class GuardTestCase(unittest.TestCase):
    config = {
        "account_id": ACCOUNT,
        "person_id": ME,
        "guard": {"protected_columns": [IN_PROGRESS, IN_REVIEW, DONE, CLOSING]},
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"BASECAMP_MANAGER_HOME": self.tmp.name}
        self.write_config(self.config)
        for key in list(os.environ):
            if key.startswith("CLAUDE_PLUGIN_OPTION_"):
                self.env[key] = None
        self.saved = {key: os.environ.get(key) for key in self.env}
        self.apply_env()
        self.addCleanup(self.restore_env)
        self.token = os.path.join(self.tmp.name, "token")
        self.oauth = os.path.join(self.tmp.name, "oauth.json")

    def write_config(self, config):
        with open(os.path.join(self.tmp.name, "config.json"), "w") as handle:
            json.dump(config, handle)

    def apply_env(self):
        for key, value in self.env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def restore_env(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def option(self, key, value):
        os.environ[f"CLAUDE_PLUGIN_OPTION_{key.upper()}"] = value

    def bash(self, command):
        return guard.decide({"tool_name": "Bash", "tool_input": {"command": command}})

    def curl(self, method, path, body=None):
        command = f'curl -s -X {method} -H "Authorization: Bearer $(cat {self.token})" "{BASE}{path}"'
        if body is not None:
            command += f" -d '{json.dumps(body)}'"
        return self.bash(command)

    def assertAllowed(self, reason):
        self.assertIsNone(reason)

    def assertDenied(self, reason, fragment=""):
        self.assertIsNotNone(reason, "expected a deny")
        self.assertIn(fragment, reason)


class TestProjectCases(GuardTestCase):
    """The 21 cases from the project definition (section 8.4)."""

    def test_01_claim_unassigned_card_in_normal_column(self):
        self.assertAllowed(self.curl("PUT", "/card_tables/cards/10.json", {"assignee_ids": [ME]}))

    def test_02_claim_in_another_normal_column(self):
        self.assertAllowed(self.curl("PUT", "/card_tables/cards/11.json", {"assignee_ids": [ME]}))

    def test_03_claim_and_change_title_in_same_call(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/10.json", {"assignee_ids": [ME], "title": "x"}))

    def test_04_change_title_of_unassigned_card(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/10.json", {"title": "x"}), "not assigned to you")

    def test_05_assign_unassigned_card_to_someone_else(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/10.json", {"assignee_ids": [OTHER]}))

    def test_06_assign_to_me_and_someone_else(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/10.json", {"assignee_ids": [ME, OTHER]}))

    def test_07_body_from_a_file(self):
        command = f'curl -s -X PUT "{BASE}/card_tables/cards/10.json" -d @/tmp/body.json'
        self.assertDenied(self.bash(command))

    def test_08_claim_in_progress(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/12.json", {"assignee_ids": [ME]}), "protected")

    def test_09_claim_in_review(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/13.json", {"assignee_ids": [ME]}))

    def test_10_claim_done(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/14.json", {"assignee_ids": [ME]}))

    def test_11_claim_closing_column(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/15.json", {"assignee_ids": [ME]}))

    def test_12_claim_card_assigned_to_someone_else(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/16.json", {"assignee_ids": [ME]}))

    def test_13_move_unassigned_card(self):
        self.assertDenied(self.curl("POST", "/card_tables/cards/10/moves.json", {"column_id": TODO}))

    def test_14_add_step_to_unassigned_card(self):
        self.assertDenied(self.curl("POST", "/card_tables/cards/10/steps.json", {"title": "x"}))

    def test_15_comment_on_unassigned_card(self):
        self.assertDenied(self.curl("POST", "/recordings/10/comments.json", {"content": "<p>x</p>"}))

    def test_16_delete_card(self):
        self.assertDenied(self.curl("DELETE", "/card_tables/cards/20.json"), "deleting")

    def test_17_trash_card(self):
        self.assertDenied(self.curl("PUT", "/recordings/20/status/trashed.json"), "trashing")

    def test_18_edit_title_of_my_card(self):
        self.assertAllowed(self.curl("PUT", "/card_tables/cards/20.json", {"title": "x"}))

    def test_19_move_my_card(self):
        self.assertAllowed(self.curl("POST", "/card_tables/cards/20/moves.json", {"column_id": IN_REVIEW}))

    def test_20_edit_someone_elses_card(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/16.json", {"title": "x"}))

    def test_21_read_unassigned_card(self):
        self.assertAllowed(self.curl("GET", "/card_tables/cards/10.json"))


class TestOwnership(GuardTestCase):

    def test_shared_card_where_i_am_one_assignee(self):
        self.assertAllowed(self.curl("POST", "/card_tables/cards/21/steps.json", {"title": "x"}))

    def test_create_card(self):
        self.assertAllowed(self.curl("POST", f"/card_tables/lists/{TODO}/cards.json", {"title": "x"}))

    def test_legacy_bucket_route(self):
        self.assertAllowed(self.curl("PUT", "/buckets/77/card_tables/cards/20.json", {"title": "x"}))

    def test_card_i_created_stays_editable_while_unassigned(self):
        self.assertAllowed(self.curl("POST", "/card_tables/cards/31/steps.json", {"title": "x"}))

    def test_card_i_created_in_protected_column(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/32.json", {"title": "x"}))

    def test_complete_step_of_my_card(self):
        self.assertAllowed(self.curl("PUT", "/card_tables/steps/500/completions.json", {"completion": "on"}))

    def test_complete_step_of_someone_elses_card(self):
        self.assertDenied(self.curl("PUT", "/card_tables/steps/501/completions.json", {"completion": "on"}))

    def test_unknown_card_fails_closed(self):
        self.assertDenied(self.curl("PUT", "/card_tables/cards/999.json", {"title": "x"}), "could not verify")

    def test_comment_on_my_card(self):
        self.assertAllowed(self.curl("POST", "/recordings/20/comments.json", {"content": "<p>x</p>"}))

    def test_edit_comment(self):
        self.assertDenied(self.curl("PUT", "/recordings/20/comments.json", {"content": "x"}), "only be created")


class TestOptions(GuardTestCase):

    def test_claim_turned_off(self):
        self.option("allow_claim", "false")
        self.assertDenied(self.curl("PUT", "/card_tables/cards/10.json", {"assignee_ids": [ME]}))

    def test_comments_turned_off(self):
        self.option("allow_comments", "false")
        self.assertDenied(self.curl("POST", "/recordings/20/comments.json", {"content": "x"}), "allow_comments")

    def test_edit_window_for_my_unassigned_cards(self):
        self.option("own_unassigned_edit_minutes", "15")
        self.assertAllowed(self.curl("POST", "/card_tables/cards/30/steps.json", {"title": "x"}))
        self.assertDenied(self.curl("POST", "/card_tables/cards/31/steps.json", {"title": "x"}))

    def test_config_file_guard_section(self):
        self.write_config({**self.config, "guard": {**self.config["guard"], "allow_claim": False}})
        self.assertDenied(self.curl("PUT", "/card_tables/cards/10.json", {"assignee_ids": [ME]}))

    def test_not_configured_blocks_writes_but_not_reads(self):
        os.remove(os.path.join(self.tmp.name, "config.json"))
        self.assertDenied(self.curl("PUT", "/card_tables/cards/20.json", {"title": "x"}), "not configured")
        self.assertAllowed(self.bash("curl -s https://3.basecampapi.com/authorization.json"))

    def test_broken_config_fails_closed(self):
        with open(os.path.join(self.tmp.name, "config.json"), "w") as handle:
            handle.write("{nope")
        self.assertDenied(self.curl("GET", "/card_tables/cards/20.json"), "not valid JSON")


class TestShellShapes(GuardTestCase):

    def test_host_outside_curl(self):
        self.assertDenied(self.bash(f'echo "{BASE}/card_tables/cards/1.json"'), "curl")

    def test_curl_wrapped_in_bash_c(self):
        self.assertDenied(self.bash(f'bash -c "curl -X DELETE {BASE}/card_tables/cards/20.json"'))

    def test_python_against_host(self):
        self.assertDenied(self.bash(f"python3 -c 'import urllib.request; urllib.request.urlopen(\"{BASE}\")'"))

    def test_attached_method_flag(self):
        self.assertDenied(self.bash(f"curl -XDELETE {BASE}/card_tables/cards/20.json"), "deleting")

    def test_long_method_flag(self):
        self.assertDenied(self.bash(f"curl --request=DELETE {BASE}/card_tables/cards/20.json"), "deleting")

    def test_data_implies_post(self):
        self.assertDenied(self.bash(f"curl {BASE}/card_tables/cards/16/steps.json -d '{{\"title\":\"x\"}}'"))

    def test_upload_implies_put(self):
        self.assertDenied(self.bash(f"curl -T body.json {BASE}/card_tables/cards/16.json"))

    def test_unknown_write_endpoint(self):
        self.assertDenied(self.curl("POST", "/attachments.json", {}), "not an allowed write endpoint")

    def test_wrong_method_on_known_endpoint(self):
        self.assertDenied(self.curl("PATCH", "/card_tables/cards/20.json", {"title": "x"}))

    def test_other_account(self):
        command = f"curl -X PUT https://3.basecampapi.com/999/card_tables/cards/20.json -d '{{}}'"
        self.assertDenied(self.bash(command), "outside account")

    def test_curl_config_file(self):
        self.assertDenied(self.bash(f"curl -K evil.cfg {BASE}/card_tables/cards/20.json"), "config")

    def test_chained_read_then_delete(self):
        command = f"curl -s {BASE}/card_tables/cards/20.json && curl -X DELETE {BASE}/card_tables/cards/20.json"
        self.assertDenied(self.bash(command), "deleting")

    def test_read_piped_to_jq(self):
        self.assertAllowed(self.bash(f'curl -s "{BASE}/card_tables/cards/20.json" | jq .title'))

    def test_unrelated_command(self):
        self.assertAllowed(self.bash("git status && ls -la"))


class TestSecrets(GuardTestCase):

    def test_token_variable_used_by_curl(self):
        command = f'T=$(cat {self.token}); curl -s -H "Authorization: Bearer $T" "{BASE}/projects.json" | jq .'
        self.assertAllowed(self.bash(command))

    def test_print_token(self):
        self.assertDenied(self.bash(f"cat {self.token}"), "token file")

    def test_token_variable_echoed(self):
        self.assertDenied(self.bash(f'T=$(cat {self.token}); echo "$T"'), "token")

    def test_token_sent_to_url_in_variable(self):
        command = f'T=$(cat {self.token}); U="{BASE}/card_tables/cards/16.json"; curl -X DELETE -H "Bearer $T" "$U"'
        self.assertDenied(self.bash(command))

    def test_token_given_to_another_program(self):
        self.assertDenied(self.bash(f'T=$(cat {self.token}) python3 send.py'))

    def test_token_copied(self):
        self.assertDenied(self.bash(f"cp {self.token} /tmp/x"), "token file")

    def test_oauth_secrets_file(self):
        self.assertDenied(self.bash(f"jq . {self.oauth}"), "OAuth")

    def test_read_tool_on_token(self):
        self.assertDenied(guard.decide({"tool_name": "Read", "tool_input": {"file_path": self.token}}))

    def test_grep_over_parent_directory(self):
        self.assertDenied(guard.decide({"tool_name": "Grep", "tool_input": {"pattern": "x", "path": self.tmp.name}}))

    def test_read_tool_on_config_is_fine(self):
        path = os.path.join(self.tmp.name, "config.json")
        self.assertAllowed(guard.decide({"tool_name": "Read", "tool_input": {"file_path": path}}))


if __name__ == "__main__":
    unittest.main()
