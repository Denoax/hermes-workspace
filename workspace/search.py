"""Keyless, explicit Wikipedia search. Fixed public provider; no arbitrary fetch API."""
import http.client,ipaddress,json,socket,ssl,urllib.parse

HOST='en.wikipedia.org'


def public_addresses(host):
    addresses={r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise ValueError('public_DNS_destination_required')
    return sorted(addresses)


class PublicHTTPS(http.client.HTTPSConnection):
    def connect(self):
        address=public_addresses(self.host)[0]
        self.sock=ssl.create_default_context().wrap_socket(socket.create_connection((address,443),timeout=self.timeout),server_hostname=self.host)


def search(query):
    if type(query) is not str or not 1<=len(query.strip())<=200 or any(ord(c)<32 for c in query):raise ValueError('bounded_explicit_search_query_required')
    c=PublicHTTPS(HOST,timeout=8)
    try:
        params=urllib.parse.urlencode({'action':'query','generator':'search','gsrsearch':query,'gsrlimit':4,'prop':'extracts|info','exintro':1,'explaintext':1,'exchars':1200,'inprop':'url','format':'json'})
        c.request('GET','/w/api.php?'+params,headers={'User-Agent':'HermesWorkspace/1.0 (local personal assistant; Wikipedia search)'})
        r=c.getresponse();raw=r.read(128*1024+1)
        # Redirects are refused; this provider's canonical endpoint needs none.
        if r.status!=200 or len(raw)>128*1024:raise RuntimeError('Wikipedia_search_unavailable')
        rows=json.loads(raw).get('query',{}).get('pages',{})
        result=[]
        for page in sorted(rows.values(),key=lambda p:p.get('index',0)):
            url=page.get('fullurl','');parsed=urllib.parse.urlsplit(url)
            if parsed.scheme!='https' or parsed.hostname!=HOST or parsed.username or parsed.password:continue
            result.append({'id':str(page['pageid']),'title':page['title'][:180],'url':url,'text':page.get('extract','')[:1500]})
        return {'provider':'Wikipedia','query':query,'sources':result}
    finally:c.close()
