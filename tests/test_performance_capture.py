"""Complete, bounded observation transfer with a fake browser transport."""
import base64,hashlib,json,unittest
from unittest.mock import Mock
from scripts.performance_capture import stop_performance,CHUNK_BYTES,MAX_BYTES

class Transfer(unittest.TestCase):
    def browser(self, value):
        raw=json.dumps(value,ensure_ascii=False).encode()
        chunks=[base64.b64encode(raw[i:i+CHUNK_BYTES]).decode() for i in range(0,len(raw),CHUNK_BYTES)]
        return Mock(evaluate=Mock(side_effect=[{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},*chunks,True]))

    def test_long_report_and_unicode_are_preserved_exactly_in_bounded_chunks(self):
        value={'frames':[i/7 for i in range(20000)],'label':'motion → 🧠'}
        browser=self.browser(value)
        self.assertEqual(stop_performance(browser),value)
        self.assertGreater(browser.evaluate.call_count,3)
        self.assertTrue(all('subarray' in row.args[0] for row in browser.evaluate.call_args_list[1:-1]))

    def test_invalid_size_or_digest_stops_before_any_chunk(self):
        for metadata in [{'bytes':MAX_BYTES+1,'sha256':'a'*64},{'bytes':True,'sha256':'a'*64},{'bytes':2,'sha256':'invalid'}]:
            browser=Mock(evaluate=Mock(return_value=metadata))
            with self.assertRaisesRegex(RuntimeError,'bounded_performance_transfer_required'):stop_performance(browser)
            self.assertEqual(browser.evaluate.call_count,1)

    def test_truncated_chunk_is_not_accepted_as_a_complete_report(self):
        browser=Mock(evaluate=Mock(side_effect=[{'bytes':2,'sha256':hashlib.sha256(b'{}').hexdigest()},base64.b64encode(b'{').decode()]))
        with self.assertRaisesRegex(RuntimeError,'chunk_length_changed'):stop_performance(browser)

    def test_mutated_sample_bytes_fail_the_full_report_hash(self):
        browser=Mock(evaluate=Mock(side_effect=[{'bytes':2,'sha256':hashlib.sha256(b'{}').hexdigest()},base64.b64encode(b'[]').decode()]))
        with self.assertRaisesRegex(RuntimeError,'transfer_hash_changed'):stop_performance(browser)

if __name__=='__main__':unittest.main()
