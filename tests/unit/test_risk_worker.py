"""Pure component fixtures; never proof of a CSE or MEC connection."""
import io
import json
import unittest
from unittest.mock import patch

from mec.risk.worker import MAX_LINE,run_stream
from tests.unit.test_evacuation import frame


class RiskWorkerTests(unittest.TestCase):
    def run_frames(self,items):
        source=io.BytesIO(b''.join(json.dumps(x).encode()+b'\n' for x in items))
        destination=io.StringIO();summary=run_stream(source,destination)
        return summary,[json.loads(line) for line in destination.getvalue().splitlines()]

    def test_consecutive_frames_produce_current_correlated_model(self):
        summary,rows=self.run_frames([frame().to_dict(),frame(1).to_dict()])
        self.assertEqual(summary['state'],'PASS');self.assertEqual(summary['accepted'],2)
        self.assertEqual([r['result']['route_version'] for r in rows],[1,2])
        self.assertEqual(rows[-1]['result']['population']['total'],170)
        self.assertEqual(rows[-1]['CSE'],'NOT_CONTACTED');self.assertEqual(rows[-1]['MEC'],'NOT_CONTACTED')

    def test_duplicate_does_not_reissue_snapshot_or_refresh_timestamp(self):
        a=frame().to_dict();summary,rows=self.run_frames([a,a,frame(1).to_dict()])
        self.assertEqual(summary['duplicates'],1)
        self.assertEqual(rows[1]['processing_state'],'DUPLICATE');self.assertIsNone(rows[1]['result'])

    def test_skipped_or_old_frame_stops_with_no_current_direction(self):
        for items in [[frame().to_dict(),frame(2).to_dict()],
                      [frame().to_dict(),frame(1).to_dict(),frame().to_dict()]]:
            summary,rows=self.run_frames(items)
            self.assertEqual(summary['state'],'FAIL')
            self.assertEqual(rows[-1]['guidance_status'],'UNKNOWN')
            self.assertIsNone(rows[-1]['result']);self.assertIsNone(rows[-1]['route'])

    def test_context_change_requires_a_new_worker(self):
        b=frame(1).to_dict();b['incident_id']='inc-another'
        summary,rows=self.run_frames([frame().to_dict(),b])
        self.assertEqual(summary['state'],'FAIL');self.assertEqual(rows[-1]['processing_state'],'REJECTED')

    def test_invalid_payload_is_not_echoed_in_rejection(self):
        source=io.BytesIO(b'{"private-fixture-value": broken}\n');out=io.StringIO()
        summary=run_stream(source,out)
        self.assertEqual(summary['state'],'FAIL');self.assertNotIn('private-fixture-value',out.getvalue())

    def test_oversized_or_unterminated_line_fails(self):
        for value in [b'x'*(MAX_LINE+1),json.dumps(frame().to_dict()).encode()]:
            out=io.StringIO();summary=run_stream(io.BytesIO(value),out)
            self.assertEqual(summary['state'],'FAIL');self.assertIsNone(json.loads(out.getvalue())['result'])

    def test_empty_input_cannot_claim_success(self):
        out=io.StringIO();summary=run_stream(io.BytesIO(),out)
        self.assertEqual(summary['state'],'FAIL')

    def test_deeply_nested_JSON_is_rejected_with_unknown_guidance(self):
        out=io.StringIO();summary=run_stream(io.BytesIO(b'['*4000+b']'*4000+b'\n'),out)
        self.assertEqual(summary['state'],'FAIL')
        self.assertEqual(json.loads(out.getvalue())['guidance_status'],'UNKNOWN')

    def test_missing_explicit_assumptions_file_does_not_use_default(self):
        from mec.risk.worker import main
        out=io.StringIO()
        with patch('sys.argv',['worker','--assumptions','/not-present/private-fixture-value.json']),patch('sys.stdout',out),patch('sys.stderr',io.StringIO()):
            self.assertEqual(main(),2)
        self.assertNotIn('private-fixture-value',out.getvalue())
        self.assertEqual(json.loads(out.getvalue())['reason'],'INVALID_ASSUMPTIONS')

    def test_valid_input_uses_no_network_socket(self):
        with patch('socket.socket',side_effect=AssertionError('Network must not be used')):
            summary,rows=self.run_frames([frame().to_dict()])
        self.assertEqual(summary['state'],'PASS')

    def test_no_route_has_null_exit_and_empty_path(self):
        b=frame(1,changes={'F7-SA':{'fire_index':60},'F7-SB':{'fire_index':60}}).to_dict()
        summary,rows=self.run_frames([frame().to_dict(),b]);route=rows[-1]['result']['fixed_route']
        self.assertEqual(summary['state'],'PASS');self.assertEqual(route['status'],'NO_VERIFIED_ROUTE')
        self.assertIsNone(route['target_exit']);self.assertEqual(route['path'],[])


if __name__=='__main__':unittest.main()
