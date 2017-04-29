from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import BufferWARCWriter
from warcio.recordloader import ArcWarcRecordLoader
from warcio.archiveiterator import ArchiveIterator
from warcio.bufferedreaders import DecompressingBufferedReader

from . import get_test_file

from io import BytesIO
from collections import OrderedDict
import json
from six import next

import pytest


# ============================================================================
class FixedTestWARCWriter(BufferWARCWriter):
    @classmethod
    def _make_warc_id(cls, id_=None):
        return '<urn:uuid:12345678-feb0-11e6-8f83-68a86d1772ce>'

    @classmethod
    def _make_warc_date(cls):
        return '2000-01-01T00:00:00Z'


# ============================================================================
WARCINFO_RECORD = '\
WARC/1.0\r\n\
WARC-Type: warcinfo\r\n\
WARC-Record-ID: <urn:uuid:12345678-feb0-11e6-8f83-68a86d1772ce>\r\n\
WARC-Filename: testfile.warc.gz\r\n\
WARC-Date: 2000-01-01T00:00:00Z\r\n\
Content-Type: application/warc-fields\r\n\
Content-Length: 86\r\n\
\r\n\
software: recorder test\r\n\
format: WARC File Format 1.0\r\n\
json-metadata: {"foo": "bar"}\r\n\
\r\n\
\r\n\
'


RESPONSE_RECORD = '\
WARC/1.0\r\n\
WARC-Type: response\r\n\
WARC-Record-ID: <urn:uuid:12345678-feb0-11e6-8f83-68a86d1772ce>\r\n\
WARC-Target-URI: http://example.com/\r\n\
WARC-Date: 2000-01-01T00:00:00Z\r\n\
WARC-Payload-Digest: sha1:B6QJ6BNJ3R4B23XXMRKZKHLPGJY2VE4O\r\n\
WARC-Block-Digest: sha1:OS3OKGCWQIJOAOC3PKXQOQFD52NECQ74\r\n\
Content-Type: application/http; msgtype=response\r\n\
Content-Length: 97\r\n\
\r\n\
HTTP/1.0 200 OK\r\n\
Content-Type: text/plain; charset="UTF-8"\r\n\
Custom-Header: somevalue\r\n\
\r\n\
some\n\
text\
\r\n\
\r\n\
'


REQUEST_RECORD = '\
WARC/1.0\r\n\
WARC-Type: request\r\n\
WARC-Record-ID: <urn:uuid:12345678-feb0-11e6-8f83-68a86d1772ce>\r\n\
WARC-Target-URI: http://example.com/\r\n\
WARC-Date: 2000-01-01T00:00:00Z\r\n\
WARC-Payload-Digest: sha1:3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ\r\n\
WARC-Block-Digest: sha1:ONEHF6PTXPTTHE3333XHTD2X45TZ3DTO\r\n\
Content-Type: application/http; msgtype=request\r\n\
Content-Length: 54\r\n\
\r\n\
GET / HTTP/1.0\r\n\
User-Agent: foo\r\n\
Host: example.com\r\n\
\r\n\
\r\n\
\r\n\
'


REVISIT_RECORD_1 = '\
WARC/1.0\r\n\
WARC-Type: revisit\r\n\
WARC-Record-ID: <urn:uuid:12345678-feb0-11e6-8f83-68a86d1772ce>\r\n\
WARC-Target-URI: http://example.com/\r\n\
WARC-Date: 2000-01-01T00:00:00Z\r\n\
WARC-Profile: http://netpreserve.org/warc/1.0/revisit/identical-payload-digest\r\n\
WARC-Refers-To-Target-URI: http://example.com/foo\r\n\
WARC-Refers-To-Date: 1999-01-01T00:00:00Z\r\n\
WARC-Payload-Digest: sha1:B6QJ6BNJ3R4B23XXMRKZKHLPGJY2VE4O\r\n\
WARC-Block-Digest: sha1:3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ\r\n\
Content-Type: application/http; msgtype=response\r\n\
Content-Length: 0\r\n\
\r\n\
\r\n\
\r\n\
'


REVISIT_RECORD_2 = '\
WARC/1.0\r\n\
WARC-Type: revisit\r\n\
WARC-Record-ID: <urn:uuid:12345678-feb0-11e6-8f83-68a86d1772ce>\r\n\
WARC-Target-URI: http://example.com/\r\n\
WARC-Date: 2000-01-01T00:00:00Z\r\n\
WARC-Profile: http://netpreserve.org/warc/1.0/revisit/identical-payload-digest\r\n\
WARC-Refers-To-Target-URI: http://example.com/foo\r\n\
WARC-Refers-To-Date: 1999-01-01T00:00:00Z\r\n\
WARC-Payload-Digest: sha1:B6QJ6BNJ3R4B23XXMRKZKHLPGJY2VE4O\r\n\
WARC-Block-Digest: sha1:A6J5UTI2QHHCZFCFNHQHCDD3JJFKP53V\r\n\
Content-Type: application/http; msgtype=response\r\n\
Content-Length: 88\r\n\
\r\n\
HTTP/1.0 200 OK\r\n\
Content-Type: text/plain; charset="UTF-8"\r\n\
Custom-Header: somevalue\r\n\
\r\n\
\r\n\
\r\n\
'

RESOURCE_RECORD = '\
WARC/1.0\r\n\
WARC-Type: resource\r\n\
WARC-Record-ID: <urn:uuid:12345678-feb0-11e6-8f83-68a86d1772ce>\r\n\
WARC-Target-URI: ftp://example.com/\r\n\
WARC-Date: 2000-01-01T00:00:00Z\r\n\
WARC-Payload-Digest: sha1:B6QJ6BNJ3R4B23XXMRKZKHLPGJY2VE4O\r\n\
WARC-Block-Digest: sha1:B6QJ6BNJ3R4B23XXMRKZKHLPGJY2VE4O\r\n\
Content-Type: text/plain\r\n\
Content-Length: 9\r\n\
\r\n\
some\n\
text\
\r\n\
\r\n\
'



# ============================================================================
class TestWarcWriter(object):
    @classmethod
    def setup_class(cls):
        cls.samples = {'response': (cls._sample_response, RESPONSE_RECORD),
                       'request': (cls._sample_request, REQUEST_RECORD),
                       'resource': (cls._sample_resource, RESOURCE_RECORD),
                       'revisit_1': (cls._sample_revisit_1, REVISIT_RECORD_1),
                       'revisit_2': (cls._sample_revisit_2, REVISIT_RECORD_2),
                      }

    @classmethod
    def _validate_record_content_len(cls, stream):
        for record in ArchiveIterator(stream, no_record_parse=True):
            assert record.http_headers == None
            assert int(record.rec_headers.get_header('Content-Length')) == record.length
            assert record.length == len(record.raw_stream.read())


    @classmethod
    def _sample_response(cls, writer):
        headers_list = [('Content-Type', 'text/plain; charset="UTF-8"'),
                        ('Custom-Header', 'somevalue')
                       ]

        payload = b'some\ntext'

        http_headers = StatusAndHeaders('200 OK', headers_list, protocol='HTTP/1.0')

        record = writer.create_warc_record('http://example.com/', 'response',
                                           payload=BytesIO(payload),
                                           length=len(payload),
                                           http_headers=http_headers)

        return record

    @classmethod
    def _sample_request(cls, writer):
        headers_list = [('User-Agent', 'foo'),
                        ('Host', 'example.com')]

        http_headers = StatusAndHeaders('GET / HTTP/1.0', headers_list)

        record = writer.create_warc_record('http://example.com/', 'request',
                                           http_headers=http_headers)
        return record

    @classmethod
    def _sample_resource(cls, writer):
        payload = b'some\ntext'

        record = writer.create_warc_record('ftp://example.com/', 'resource',
                                           payload=BytesIO(payload),
                                           length=len(payload),
                                           warc_content_type='text/plain')

        return record

    @classmethod
    def _sample_revisit_1(cls, writer):
        record = writer.create_revisit_record('http://example.com/',
                                              digest='sha1:B6QJ6BNJ3R4B23XXMRKZKHLPGJY2VE4O',
                                              refers_to_uri='http://example.com/foo',
                                              refers_to_date='1999-01-01T00:00:00Z')

        return record

    @classmethod
    def _sample_revisit_2(cls, writer):
        resp = cls._sample_response(writer)

        record = writer.create_revisit_record('http://example.com/',
                                              digest='sha1:B6QJ6BNJ3R4B23XXMRKZKHLPGJY2VE4O',
                                              refers_to_uri='http://example.com/foo',
                                              refers_to_date='1999-01-01T00:00:00Z',
                                              http_headers=resp.http_headers)
        return record


    @pytest.mark.parametrize("gzip", ['gzip', 'plain'])
    def test_warcinfo_record(self, gzip):
        writer = FixedTestWARCWriter(gzip=(gzip=='gzip'))
        params = OrderedDict([('software', 'recorder test'),
                              ('format', 'WARC File Format 1.0'),
                              ('invalid', ''),
                              ('json-metadata', json.dumps({'foo': 'bar'}))])

        record = writer.create_warcinfo_record('testfile.warc.gz', params)
        writer.write_record(record)
        reader = DecompressingBufferedReader(writer.get_stream())

        parsed_record = ArcWarcRecordLoader().parse_record_stream(reader)

        assert parsed_record.rec_headers.get_header('WARC-Type') == 'warcinfo'
        assert parsed_record.rec_headers.get_header('Content-Type') == 'application/warc-fields'
        assert parsed_record.rec_headers.get_header('WARC-Filename') == 'testfile.warc.gz'

        buff = parsed_record.raw_stream.read().decode('utf-8')

        length = parsed_record.rec_headers.get_header('Content-Length')

        assert len(buff) == int(length)

        assert 'json-metadata: {"foo": "bar"}\r\n' in buff
        assert 'format: WARC File Format 1.0\r\n' in buff

        reader = DecompressingBufferedReader(writer.get_stream())
        assert reader.read().decode('utf-8') == WARCINFO_RECORD

    @pytest.mark.parametrize("rec_type", ['response', 'request', 'resource', 'revisit_1', 'revisit_2'])
    def test_generate_record(self, rec_type):
        writer = FixedTestWARCWriter(gzip=False)

        func, record_string = self.samples[rec_type]
        record = func(writer)

        writer.write_record(record)

        buff = writer.get_contents()

        self._validate_record_content_len(BytesIO(buff))

        assert buff.decode('utf-8') == record_string

        # assert parsing record matches as well
        parsed_record = ArcWarcRecordLoader().parse_record_stream(writer.get_stream())
        writer2 = FixedTestWARCWriter(gzip=False)
        writer2.write_record(parsed_record)
        assert writer2.get_contents().decode('utf-8') == record_string

    @pytest.mark.parametrize("rec_type", ['response', 'request', 'resource', 'revisit_1', 'revisit_2'])
    def test_generate_record_gzip(self, rec_type):
        writer = FixedTestWARCWriter(gzip=True)

        func, record_string = self.samples[rec_type]
        record = func(writer)

        writer.write_record(record)

        gzip_buff = writer.get_contents()

        self._validate_record_content_len(BytesIO(gzip_buff))

        stream = DecompressingBufferedReader(writer.get_stream())

        buff = stream.read()
        assert len(buff) > len(gzip_buff)

        assert buff.decode('utf-8') == record_string

        # assert parsing record matches as well
        stream = DecompressingBufferedReader(writer.get_stream())

        parsed_record = ArcWarcRecordLoader().parse_record_stream(stream)
        writer2 = FixedTestWARCWriter(gzip=False)
        writer2.write_record(parsed_record)
        assert writer2.get_contents().decode('utf-8') == record_string

    @pytest.mark.parametrize("gzip", ['gzip', 'plain'])
    def test_request_response_concur(self, gzip):
        writer = BufferWARCWriter(gzip=(gzip=='gzip'))

        resp = self._sample_response(writer)

        req = self._sample_request(writer)

        writer.write_request_response_pair(req, resp)

        stream = writer.get_stream()

        reader = ArchiveIterator(stream)
        resp, req = list(reader)

        resp_id = resp.rec_headers.get_header('WARC-Record-ID')
        req_id = req.rec_headers.get_header('WARC-Record-ID')

        assert resp_id != req_id
        assert resp_id == req.rec_headers.get_header('WARC-Concurrent-To')

    def test_copy_from_stream(self):
        writer = FixedTestWARCWriter(gzip=False)

        stream = BytesIO()

        # strip-off the two empty \r\n\r\n added at the end of uncompressed record
        stream.write(RESPONSE_RECORD[:-4].encode('utf-8'))

        length = stream.tell()
        stream.seek(0)

        record = writer.create_record_from_stream(stream, length)

        writer.write_record(record)

        buff = writer.get_contents()

        assert buff.decode('utf-8') == RESPONSE_RECORD

    def test_arc2warc(self):
        writer = FixedTestWARCWriter(gzip=False)

        with open(get_test_file('example.arc.gz'), 'rb') as fh:
            for record in ArchiveIterator(fh, arc2warc=True):
                writer.write_record(record)

            buff = writer.get_contents()

        self._validate_record_content_len(BytesIO(buff))

        buff = buff.decode('utf-8')

        assert 'WARC-Filename: live-web-example.arc.gz' in buff
        assert 'Content-Type: text/plain' in buff

        assert 'WARC-Target-URI: http://example.com/' in buff

