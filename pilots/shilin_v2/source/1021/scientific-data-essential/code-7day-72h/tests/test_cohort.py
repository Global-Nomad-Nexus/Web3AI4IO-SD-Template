import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mvp.acquire_chain import PUMPFUN_PROGRAM_ID, _base58_encode, decode_transaction
from mvp.build_release import build_coverage_ledger, parse_field_observations
from mvp.common import read_csv, read_json, read_jsonl
from mvp.live_cohort import discover_window_events, run_live_cohort
from mvp.observe_metadata import FetchResult, FixtureTransport, build_observation_plan, observe_events
from mvp.schedule import assert_window_joinable, plan_rows, runtime_budget_seconds, validate_protocol
from mvp.schema import ATTEMPT_FIELDS, PLAN_FIELDS, SNAPSHOT_FIELDS


class CohortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.protocol = read_json(ROOT / "configs/mvp_protocol.json")
        self.sources = read_csv(ROOT / "configs/source_register.csv")
        self.events = json.loads((ROOT / "fixtures/sample_events.json").read_text())

    def test_protocol_is_seven_utc_days_and_four_checkpoints(self):
        start, end = validate_protocol(self.protocol)
        self.assertEqual(start, datetime(2026, 10, 8, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 10, 15, tzinfo=timezone.utc))
        self.assertEqual(self.protocol["observation"]["checkpoints"], ["T0", "T24", "T48", "T72"])
        broken = json.loads(json.dumps(self.protocol))
        broken["window"]["end"] = "2026-10-09T00:00:00Z"
        with self.assertRaises(ValueError):
            validate_protocol(broken)
        late = datetime(2026, 10, 8, 0, 6, tzinfo=timezone.utc)
        with self.assertRaises(SystemExit):
            assert_window_joinable(self.protocol, late)
        budget = runtime_budget_seconds(self.protocol, datetime(2026, 10, 7, 8, tzinfo=timezone.utc))
        self.assertGreater(budget, 10 * 24 * 3600)
        self.assertLess(budget, 12 * 24 * 3600)

    def test_fixture_plan_follows_block_time(self):
        plan = build_observation_plan(self.events, self.protocol)
        self.assertEqual(len(plan), 16)
        first = [row for row in plan if row["event_key"].endswith("fixture-signature-001:0:0")]
        scheduled = {row["checkpoint"]: row["scheduled_at"] for row in first}
        self.assertEqual(scheduled, {
            "T0": "2026-09-28T00:10:00Z",
            "T24": "2026-09-29T00:10:00Z",
            "T48": "2026-09-30T00:10:00Z",
            "T72": "2026-10-01T00:10:00Z",
        })
        self.assertEqual(first[0]["earliest_allowed_at"], first[0]["scheduled_at"])
        with self.assertRaises(ValueError):
            build_observation_plan(self.events, self.protocol, anchor_time="2026-10-08T00:00:00Z")

    def test_creator_comes_from_instruction_arguments(self):
        discriminator = bytes((24, 30, 200, 40, 5, 28, 7, 119))
        creator = bytes(range(32))

        def borsh_string(value):
            data = value.encode()
            return len(data).to_bytes(4, "little") + data

        raw = discriminator + borsh_string("Cumin") + borsh_string("CUM") + borsh_string("https://x.test/m.json") + creator
        accounts = ["MintPubkey", "a", "b", "c", "d", "e", "f", "IndexSevenIsNotCreator"]
        transaction = {"result": {"slot": 1, "transaction": {"message": {"accountKeys": accounts, "instructions": [{
            "programId": PUMPFUN_PROGRAM_ID,
            "accounts": accounts,
            "data": _base58_encode(raw),
        }]}}, "meta": {}}}
        decoded = decode_transaction(transaction, "sig", 1790000000)
        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0]["mint"], "MintPubkey")
        self.assertEqual(decoded[0]["creator"], _base58_encode(creator))
        self.assertNotEqual(decoded[0]["creator"], "IndexSevenIsNotCreator")
        self.assertEqual(decoded[0]["decoder_version"], "pumpfun-create-borsh-v2")

    def test_followup_before_chain_time_is_early(self):
        event = dict(self.events[0])
        rows = plan_rows(event, self.protocol, seen_at=datetime(2026, 9, 28, 0, 12, tzinfo=timezone.utc))
        t24 = next(row for row in rows if row["checkpoint"] == "T24")
        self.assertEqual(t24["earliest_allowed_at"], "2026-09-29T00:10:00Z")
        self.assertEqual(rows[0]["checkpoint"], "T0")
        self.assertEqual(rows[0]["scheduled_at"], "2026-09-28T00:12:00Z")
        attempt = {
            "request_id": "req", "event_key": event["event_key"], "checkpoint": "T24", "uri": event["metadata_uri"],
            "request_url": event["metadata_uri"], "route_id": "declared_exact", "host": "metadata.example.test",
            "attempt": "1", "started_at": "2026-09-28T12:00:00Z", "completed_at": "2026-09-28T12:00:01Z",
            "available_at": "2026-09-28T12:00:01Z", "status": "success", "http_status": "200",
            "redirect_location": "", "response_bytes": "2", "response_sha256": "abc", "retry_after_seconds": "",
            "error_class": "", "error_message": "", "policy_state": "",
        }
        snapshot = {
            "request_id": "req", "event_key": event["event_key"], "checkpoint": "T24", "uri": event["metadata_uri"],
            "request_url": event["metadata_uri"], "route_id": "declared_exact", "retrieved_at": "2026-09-28T12:00:01Z",
            "content_type": "application/json", "response_sha256": "abc", "response_bytes": "2",
            "parse_state": "json_ok", "integrity_state": "not_applicable",
        }
        ledger = build_coverage_ledger([t24], [attempt], [snapshot], [])
        self.assertEqual(ledger[0]["timing_state"], "early_prohibited")
        self.assertEqual(ledger[0]["final_state"], "early_prohibited")

    def test_live_schedule_uses_each_events_block_time(self):
        protocol = json.loads(json.dumps(self.protocol))
        protocol["observation"]["poll_seconds"] = 6 * 3600
        protocol["observation"]["autosave_seconds"] = 7 * 24 * 3600
        start = datetime(2026, 10, 8, tzinfo=timezone.utc)
        chain = datetime(2026, 10, 8, 0, 30, tzinfo=timezone.utc)
        inside = dict(self.events[0])
        inside["block_time"] = str(int(chain.timestamp()))
        outside = dict(self.events[1])
        outside["block_time"] = str(int(datetime(2026, 10, 7, 12, tzinfo=timezone.utc).timestamp()))

        class Clock:
            def __init__(self):
                self.now = start

            def __call__(self):
                return self.now.isoformat().replace("+00:00", "Z")

            def sleep(self, seconds):
                self.now += timedelta(seconds=seconds)

        clock = Clock()
        calls = {"n": 0}

        def discover(client, protocol_arg, state, window_start, window_end):
            calls["n"] += 1
            self.assertEqual(window_start, start)
            self.assertEqual(window_end, datetime(2026, 10, 15, tzinfo=timezone.utc))
            return [inside, outside] if calls["n"] == 1 else []

        mapping = {uri: ROOT / path for uri, path in protocol["fixture"]["uri_files"].items()}
        out = self.work / "live"
        events, frozen = run_live_cohort(protocol, self.sources, out, transport=FixtureTransport(mapping), clock=clock, sleep=clock.sleep, discover=discover)
        self.assertEqual(len(events), 1)
        self.assertEqual(frozen["window"]["clock"], "chain_event_time")
        self.assertEqual(frozen["window"]["start"], "2026-10-08T00:00:00Z")
        plan = read_csv(out / "observation_plan.csv", PLAN_FIELDS)
        scheduled = {row["checkpoint"]: row["scheduled_at"] for row in plan}
        self.assertEqual(scheduled["T0"], "2026-10-08T00:00:00Z")
        self.assertEqual(scheduled["T24"], "2026-10-09T00:30:00Z")
        self.assertEqual(scheduled["T48"], "2026-10-10T00:30:00Z")
        self.assertEqual(scheduled["T72"], "2026-10-11T00:30:00Z")
        attempts = read_csv(out / "request_attempts.csv", ATTEMPT_FIELDS)
        started = {row["checkpoint"]: row["started_at"] for row in attempts}
        self.assertEqual(started["T0"], "2026-10-08T00:00:00Z")
        self.assertGreaterEqual(started["T24"], scheduled["T24"])
        self.assertGreaterEqual(started["T48"], scheduled["T48"])
        self.assertGreaterEqual(started["T72"], scheduled["T72"])
        snapshots = read_csv(out / "response_snapshots.csv", SNAPSHOT_FIELDS)
        fields = parse_field_observations(events, snapshots, read_jsonl(out / "response_bodies.jsonl"), protocol)
        ledger = build_coverage_ledger(plan, attempts, snapshots, fields)
        self.assertEqual(sorted(row["checkpoint"] for row in ledger), ["T0", "T24", "T48", "T72"])
        self.assertTrue(all(row["final_state"] == "observed" for row in ledger))
        discover_calls = calls["n"]
        again, frozen_again = run_live_cohort(protocol, self.sources, out, transport=FixtureTransport(mapping), clock=clock, sleep=clock.sleep, discover=discover)
        self.assertEqual(len(again), 1)
        self.assertEqual(calls["n"], discover_calls)
        self.assertEqual(frozen_again["window"]["start"], "2026-10-08T00:00:00Z")

    def test_progress_is_saved_every_ten_minutes(self):
        protocol = json.loads(json.dumps(self.protocol))
        protocol["observation"]["poll_seconds"] = 24 * 3600
        protocol["observation"]["autosave_seconds"] = 600
        start = datetime(2026, 10, 14, 23, 40, tzinfo=timezone.utc)
        chain = datetime(2026, 10, 8, 0, 30, tzinfo=timezone.utc)
        inside = dict(self.events[0])
        inside["block_time"] = str(int(chain.timestamp()))

        class Clock:
            def __init__(self):
                self.now = start

            def __call__(self):
                return self.now.isoformat().replace("+00:00", "Z")

            def sleep(self, seconds):
                self.now += timedelta(seconds=seconds)

        clock = Clock()
        calls = {"n": 0}

        def discover(client, protocol_arg, state, window_start, window_end):
            calls["n"] += 1
            return [inside] if calls["n"] == 1 else []

        mapping = {uri: ROOT / path for uri, path in protocol["fixture"]["uri_files"].items()}
        out = self.work / "autosave"
        run_live_cohort(protocol, self.sources, out, transport=FixtureTransport(mapping), clock=clock, sleep=clock.sleep, discover=discover)
        history = read_jsonl(self.work / "progress.jsonl")
        saved = [row["saved_at"] for row in history]
        self.assertEqual(saved[:3], ["2026-10-14T23:40:00Z", "2026-10-14T23:50:00Z", "2026-10-15T00:00:00Z"])
        self.assertEqual(history[0]["stage"], "enrolling")
        self.assertEqual(history[0]["events"], 1)
        self.assertEqual(history[0]["completed_observations"], 4)
        self.assertEqual(history[-1]["stage"], "finished")
        latest = read_json(self.work / "progress.json")
        self.assertEqual(latest["saved_at"], saved[-1])
        self.assertEqual(read_json(out / "progress.json")["events"], 1)
        self.assertEqual(len(read_csv(out / "launch_events.csv")), 1)

    def test_private_host_is_refused(self):
        event = dict(self.events[0], metadata_uri="http://127.0.0.1/secret.json")
        plan = [dict(build_observation_plan([event], self.protocol)[0], event_key=event["event_key"])]
        out = self.work / "private"
        observe_events([event], plan, self.sources, self.protocol, out, transport=lambda uri: FetchResult(status="success", http_status="200", body=b"{}"), clock=lambda: "2026-10-02T00:00:00Z")
        attempts = read_csv(out / "request_attempts.csv", ATTEMPT_FIELDS)
        self.assertEqual(attempts[0]["status"], "not_collected_policy")
        self.assertEqual(attempts[0]["error_class"], "local_or_private_host")

    def test_signature_pages_resume_after_the_last_completed_page(self):
        protocol = json.loads(json.dumps(self.protocol))
        protocol["acquisition"]["page_limit"] = 2
        protocol["acquisition"]["max_pages"] = 1
        protocol["observation"]["live_tip"] = False
        pages = {
            None: [
                {"signature": "sig-a", "blockTime": 4000, "err": None},
                {"signature": "sig-b", "blockTime": 3000, "err": None},
            ],
            "sig-b": [
                {"signature": "sig-c", "blockTime": 2000, "err": None},
                {"signature": "sig-d", "blockTime": 1500, "err": None},
            ],
            "sig-d": [
                {"signature": "sig-e", "blockTime": 500, "err": None},
            ],
        }
        requested = []

        class Client:
            def call(self, method, params):
                requested.append((method, params[1].get("before") if method == "getSignaturesForAddress" else params[0]))
                if method == "getSignaturesForAddress":
                    return {"result": pages[params[1].get("before")]}
                return {"result": None}

        state = {"cursor": None, "signature_failures": {}, "page_done": []}
        window_start = datetime.fromtimestamp(1000, tz=timezone.utc)
        window_end = datetime.fromtimestamp(5000, tz=timezone.utc)
        discover_window_events(Client(), protocol, state, window_start, window_end)
        self.assertEqual(state["pending_before"], "sig-b")
        discover_window_events(Client(), protocol, state, window_start, window_end)
        self.assertEqual(state["pending_before"], "sig-d")
        discover_window_events(Client(), protocol, state, window_start, window_end)
        self.assertIsNone(state["pending_before"])
        self.assertEqual(state["cursor"], "sig-a")
        signature_calls = [item for item in requested if item[0] == "getSignaturesForAddress"]
        self.assertEqual([item[1] for item in signature_calls], [None, "sig-b", "sig-d"])

    def test_oversized_page_history_is_dropped(self):
        from mvp.live_cohort import discover_window_events

        protocol = json.loads(json.dumps(self.protocol))
        protocol["acquisition"]["page_limit"] = 2
        protocol["acquisition"]["max_pages"] = 1
        protocol["observation"]["live_tip"] = False

        class Client:
            def call(self, method, params):
                if method == "getSignaturesForAddress":
                    return {"result": []}
                return {"result": None}

        state = {"cursor": None, "signature_failures": {}, "page_done": [f"old-{i}" for i in range(50)]}
        discover_window_events(Client(), protocol, state, datetime(2026, 10, 8, tzinfo=timezone.utc), datetime(2026, 10, 15, tzinfo=timezone.utc))
        self.assertLessEqual(len(state["page_done"]), 2)

    def test_missing_resume_signature_restarts_from_the_tip(self):
        from mvp.live_cohort import discover_window_events

        protocol = json.loads(json.dumps(self.protocol))
        protocol["acquisition"]["page_limit"] = 2
        protocol["acquisition"]["max_pages"] = 1
        protocol["observation"]["live_tip"] = False
        calls = []

        class Client:
            def call(self, method, params):
                calls.append(params[1].get("before") if method == "getSignaturesForAddress" else params[0])
                if method == "getSignaturesForAddress" and params[1].get("before") == "missing-sig":
                    raise RuntimeError("RPC error: {'code': -32020, 'message': 'Transaction missing-sig not found'}")
                if method == "getSignaturesForAddress":
                    return {"result": [
                        {"signature": "sig-new", "blockTime": 2000, "err": None},
                        {"signature": "sig-old", "blockTime": 500, "err": None},
                    ]}
                return {"result": None}

        state = {"cursor": "old-tip", "pending_before": "missing-sig", "scan_tip": "old-tip", "signature_failures": {}, "page_done": ["already"]}
        window_start = datetime.fromtimestamp(1000, tz=timezone.utc)
        window_end = datetime.fromtimestamp(5000, tz=timezone.utc)
        discover_window_events(Client(), protocol, state, window_start, window_end)
        self.assertEqual(calls[0], "missing-sig")
        self.assertIsNone(calls[1])
        self.assertEqual(state["cursor"], "sig-new")

    def test_live_tip_stops_at_the_previous_cursor(self):
        from mvp.live_cohort import discover_window_events

        protocol = json.loads(json.dumps(self.protocol))
        protocol["observation"]["live_tip"] = True
        calls = []

        class Client:
            def call(self, method, params):
                if method == "getSignaturesForAddress":
                    calls.append(params[1].get("before"))
                    if params[1].get("before"):
                        raise AssertionError("live polling walked backward")
                    return {"result": [
                        {"signature": "sig-new", "blockTime": 1791418200, "err": None},
                        {"signature": "sig-known", "blockTime": 1791417600, "err": None},
                        {"signature": "sig-older", "blockTime": 1791417000, "err": None},
                    ]}
                calls.append(params[0])
                return {"result": None}

        state = {"cursor": "sig-known", "pending_before": "historical-backfill", "scan_tip": "old", "signature_failures": {}, "page_done": []}
        discover_window_events(
            Client(), protocol, state,
            datetime(2026, 10, 8, tzinfo=timezone.utc),
            datetime(2026, 10, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(calls, [None, "sig-new"])
        self.assertEqual(state["cursor"], "sig-new")
        self.assertIsNone(state["pending_before"])

    def test_missing_block_time_holes_are_the_two_long_gaps(self):
        from fill_gap import missing_ranges

        first_end = int(datetime(2026, 10, 8, 0, 29, 33, tzinfo=timezone.utc).timestamp())
        second_start = int(datetime(2026, 10, 9, 2, 11, 13, tzinfo=timezone.utc).timestamp())
        second_end = int(datetime(2026, 10, 9, 2, 25, 27, tzinfo=timezone.utc).timestamp())
        live_start = int(datetime(2026, 10, 9, 7, 34, 24, tzinfo=timezone.utc).timestamp())
        times = [first_end - 10, first_end, second_start, second_end, live_start]
        ranges = missing_ranges(times)
        self.assertEqual(ranges, [(first_end, second_start), (second_end, live_start)])

    def test_missing_resume_signature_is_recognized(self):
        from fill_gap import signature_is_missing

        error = RuntimeError("RPC error: {'code': -32020, 'message': 'Transaction abc not found'}")
        self.assertTrue(signature_is_missing(error))
        self.assertFalse(signature_is_missing(RuntimeError("RPC HTTP 429")))

    def test_pruned_historical_node_is_replaced_and_the_block_is_kept(self):
        from http.client import IncompleteRead

        from fill_gap import _slot_skipped, block_read_should_retry, read_block

        pruned = RuntimeError("RPC error: {'code': -32001, 'message': 'Block 454388525 cleaned up, does not exist on node. First available block: 456466071'}")
        self.assertTrue(block_read_should_retry(pruned))
        self.assertFalse(_slot_skipped(pruned))
        self.assertTrue(block_read_should_retry(IncompleteRead(b"abc")))
        skipped = RuntimeError("RPC error: {'message': 'Slot 9 was skipped, or missing due to ledger jump to recent snapshot'}")
        self.assertTrue(_slot_skipped(skipped))
        self.assertFalse(block_read_should_retry(skipped))

        class Client:
            def __init__(self, failures):
                self.failures = list(failures)
                self.calls = 0
                self.openers = []

            def call(self, method, params, opener=None):
                self.calls += 1
                self.openers.append(opener)
                if self.failures:
                    raise self.failures.pop(0)
                return {"result": {"blockTime": 1791420688, "transactions": []}}

        refreshes = []
        client = Client([pruned, pruned])
        block, error = read_block(client, 454388525, {}, attempts=4, pause=lambda _seconds: None, refresh=lambda: refreshes.append("new") or "connection")
        self.assertIsNone(error)
        self.assertEqual(block["blockTime"], 1791420688)
        self.assertEqual(client.calls, 3)
        self.assertEqual(client.openers, [None, "connection", "connection"])
        self.assertEqual(len(refreshes), 2)

        skipped_client = Client([skipped])
        block, error = read_block(skipped_client, 9, {}, attempts=4, pause=lambda _seconds: None, refresh=lambda: "connection")
        self.assertIsNone(block)
        self.assertIsNone(error)
        self.assertEqual(skipped_client.calls, 1)

        broken = Client([RuntimeError("RPC returned invalid JSON")])
        block, error = read_block(broken, 9, {}, attempts=4, pause=lambda _seconds: None)
        self.assertIsNone(block)
        self.assertIn("invalid JSON", str(error))
        self.assertEqual(broken.calls, 1)

    def test_hole_slots_include_margin_and_block_decode_keeps_inside_time(self):
        from fill_gap import covered_slots, events_from_block

        self.assertEqual(covered_slots(100, 200, margin=0), (101, 199))
        self.assertEqual(covered_slots(100, 200), (76, 224))
        self.assertIsNone(covered_slots(5, 6, margin=0))
        discriminator = bytes((24, 30, 200, 40, 5, 28, 7, 119))
        creator = bytes(range(32))

        def borsh_string(value):
            data = value.encode()
            return len(data).to_bytes(4, "little") + data

        raw = discriminator + borsh_string("Cumin") + borsh_string("CUM") + borsh_string("https://x.test/m.json") + creator
        accounts = [PUMPFUN_PROGRAM_ID, "MintPubkey"]
        entry = {"transaction": {"signatures": ["sig"], "message": {"accountKeys": accounts, "instructions": [{
            "programId": PUMPFUN_PROGRAM_ID, "accounts": ["MintPubkey"], "data": _base58_encode(raw),
        }]}}, "meta": {}}
        inside = events_from_block({"blockTime": 1_500, "transactions": [entry, {"transaction": entry["transaction"], "meta": {"err": "fail"}}]}, 9, [(1_000, 2_000)])
        self.assertEqual([event["transaction_signature"] for event in inside], ["sig"])
        self.assertEqual(events_from_block({"blockTime": 1_000, "transactions": [entry]}, 8, [(1_000, 2_000)]), [])

    def test_failed_rpc_route_starts_again_at_the_first_connection(self):
        from mvp.acquire_chain import FallbackRpcClient

        class Down:
            def __init__(self, route):
                self.route = route
                self.calls = 0
                self.opener = None

            def call(self, method, params):
                self.calls += 1
                raise RuntimeError(f"down {self.route['endpoint']}")

        seen = []

        def factory(route):
            seen.append(route["endpoint"])
            return Down(route)

        client = FallbackRpcClient(self.protocol, output_dir=self.work / "rpc", client_factory=factory)
        with self.assertRaises(RuntimeError):
            client.call("getSlot", [])
        self.assertEqual(client.index, 0)
        self.assertEqual(seen, [
            "https://solana-rpc.publicnode.com",
            "https://solana-rpc.publicnode.com",
            "https://api.mainnet-beta.solana.com",
        ])

    def test_fixture_run_passes_with_four_checkpoints(self):
        out = self.work / "fixture-run"
        completed = subprocess.run([sys.executable, "run_mvp.py", "--mode", "fixture", "--output", str(out)], cwd=ROOT, check=True, capture_output=True, text=True)
        self.assertIn("Run complete", completed.stdout)
        validation = read_json(out / "mvp_release" / "validation_results.json")
        self.assertEqual(validation["status"], "PASS")
        self.assertEqual(validation["event_count"], 4)
        self.assertEqual(validation["plan_rows"], 16)
        self.assertEqual(validation["field_rows"], 96)
        self.assertEqual(validation["final_state_counts"].get("request_failed"), 4)
        self.assertEqual(validation["final_state_counts"].get("observed"), 12)


if __name__ == "__main__":
    unittest.main()
