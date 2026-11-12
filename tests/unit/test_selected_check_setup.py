"""Synthetic runner-orchestration fixtures; never actual HTTP/CSE evidence."""
import unittest
from unittest.mock import Mock,call,patch
from urllib.error import URLError

from tests.integration.selected_dashboard_check import UnexpectedHTTPStatus,fresh_scenario


class SelectedCheckSetupTests(unittest.TestCase):
    def setUp(self):
        self.before={'incident_id':'inc-used','paused':False,'state':'READY','busy':False}
        self.after={'incident_id':'inc-new','paused':True,'state':'READY','busy':False}
        self.http=Mock()
        self.ready=Mock(side_effect=[self.before,self.after])

    def test_existing_running_incident_is_reset_before_initial_assertions(self):
        old,new=fresh_scenario(self.http,self.ready)
        self.assertEqual((old,new),(self.before,self.after))
        self.http.assert_called_once_with('/api/v1/scenario','responder','POST',{'action':'reset'},expect=202)
        self.assertEqual(self.ready.call_args_list,[call(),call(different='inc-used')])

    def test_paused_or_expired_existing_incident_also_requires_a_new_id(self):
        self.before['paused']=True
        fresh_scenario(self.http,self.ready)
        self.http.assert_called_once()
        self.ready.assert_called_with(different='inc-used')

    def test_only_explicit_busy_rejection_is_retried(self):
        self.http.side_effect=[UnexpectedHTTPStatus(409,'/api/v1/scenario'),{}]
        with patch('tests.integration.selected_dashboard_check.time.sleep') as sleep:
            fresh_scenario(self.http,self.ready)
        self.assertEqual(self.http.call_count,2);sleep.assert_called_once_with(.2)

    def test_http_failure_or_uncertain_transport_is_never_replayed(self):
        for error in [UnexpectedHTTPStatus(403,'/api/v1/scenario'),
                      UnexpectedHTTPStatus(500,'/api/v1/scenario'),URLError('unit transport failure')]:
            with self.subTest(error=type(error).__name__):
                self.http.reset_mock();self.http.side_effect=error
                self.ready.reset_mock(side_effect=True);self.ready.return_value=self.before
                with self.assertRaises(type(error)):fresh_scenario(self.http,self.ready)
                self.http.assert_called_once();self.ready.assert_called_once()

    def test_busy_rejections_have_a_deadline(self):
        self.http.side_effect=UnexpectedHTTPStatus(409,'/api/v1/scenario')
        with patch('tests.integration.selected_dashboard_check.time.monotonic',side_effect=[0,121]):
            with self.assertRaises(UnexpectedHTTPStatus):fresh_scenario(self.http,self.ready)
        self.http.assert_called_once()

    def test_unchanged_or_unpaused_reset_cannot_pass(self):
        for after in [self.before,{**self.after,'paused':False}]:
            with self.subTest(after=after):
                ready=Mock(side_effect=[self.before,after])
                with self.assertRaisesRegex(AssertionError,'new paused incident'):
                    fresh_scenario(self.http,ready)


if __name__=='__main__':unittest.main()
