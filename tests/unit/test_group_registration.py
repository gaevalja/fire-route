"""Regression for the observed actual ACME mid canonicalization.

Wire fixtures model the recorded CREATE shape; they are not integration proof.
"""
import json
import unittest
from urllib.parse import urlsplit

from onem2m.client import CSEClient, ProtocolError, ResourceConflict, WireResponse
from onem2m.groups import create_display_group


class GroupRegistrationTests(unittest.TestCase):
    def resources(self):
        return {'namespace':'fr_unit', 'actors':{'controller':{'path':'/unit-base/controller'}},
                'containers':{role+'/commands':{'ri':'cnt-'+role, 'path':'/unit-base/'+role+'/commands'}
                              for role in ['display-a','display-b','display-c']}}

    def client(self, fixture):
        admin=CSEClient('http://unit.invalid','C-unit-admin','4',transport=fixture)
        return admin,admin.for_actor('C-unit-controller','controller')

    def test_canonicalized_create_and_existing_group_are_accepted(self):
        fixture=CanonicalGroupWireFixture()
        admin,controller=self.client(fixture)
        resources=self.resources()
        first=create_display_group(admin,controller,resources,86400)
        second=create_display_group(admin,controller,resources,86400)
        self.assertEqual(first['ri'],second['ri'])
        self.assertEqual(set(first['resource']['mid']),{c['ri'] for c in resources['containers'].values()})
        self.assertEqual(first['resource']['cnm'],3)
        self.assertEqual(fixture.group_creates,1)

    def test_changed_member_is_rejected_without_overwrite(self):
        fixture=CanonicalGroupWireFixture()
        admin,controller=self.client(fixture)
        create_display_group(admin,controller,self.resources(),86400)
        fixture.data['/unit-base/controller/DisplayCommandGroup']['m2m:grp']['mid'][0]='other-container'
        with self.assertRaises(ResourceConflict):
            create_display_group(admin,controller,self.resources(),86400)
        self.assertEqual(fixture.group_creates,1)

    def test_duplicate_container_ids_fail_before_transport(self):
        fixture=CanonicalGroupWireFixture()
        admin,controller=self.client(fixture)
        resources=self.resources()
        resources['containers']['display-b/commands']['ri']=resources['containers']['display-a/commands']['ri']
        with self.assertRaises(ProtocolError):
            create_display_group(admin,controller,resources,86400)
        self.assertEqual(fixture.calls,0)

    def test_wrong_member_count_in_readback_is_rejected(self):
        fixture=CanonicalGroupWireFixture(wrong_count=True)
        admin,controller=self.client(fixture)
        with self.assertRaises(ProtocolError):
            create_display_group(admin,controller,self.resources(),86400)


class CanonicalGroupWireFixture:
    def __init__(self, *, wrong_count=False):
        self.data={}
        self.group_creates=0
        self.calls=0
        self.wrong_count=wrong_count

    def __call__(self,method,url,headers,body,timeout):
        self.calls+=1
        path=urlsplit(url).path
        if method=='POST':
            document=json.loads(body)
            root,attrs=next(iter(document.items()))
            value={**attrs,'ri':'acp-unit' if root=='m2m:acp' else 'grp-unit','ty':1 if root=='m2m:acp' else 9}
            if root=='m2m:grp':
                self.group_creates+=1
                value['mid']=[item.rsplit('/',1)[-1] for item in value['mid']]
                value.update(cnm=2 if self.wrong_count else 3,mtv=True)
            content={root:value}
            self.data[path+'/'+attrs['rn']]=content
            status,rsc=201,2001
        elif path in self.data:
            content,status,rsc=self.data[path],200,2000
        else:
            content,status,rsc={},404,4004
        return WireResponse(status,{'Content-Type':'application/json','X-M2M-RI':headers['X-M2M-RI'],
                                    'X-M2M-RVI':'4','X-M2M-RSC':str(rsc)},json.dumps(content).encode())
