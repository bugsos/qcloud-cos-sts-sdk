# -*- coding:utf-8 -*-

import hashlib
import hmac
import time
try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+
from functools import reduce
import json
import base64
import requests
import random

class Sts:

    def __init__(self, config={}):
        if 'allow_actions' in config:
            self.allow_actions = config.get('allow_actions')
        # else:
        #     raise ValueError('missing allow_actions')

        if 'duration_seconds' in config:
            self.duration = config.get('duration_seconds')
        else:
            self.duration = 1800

        self.sts_url = 'sts.tencentcloudapi.com/'
        self.sts_scheme = 'https://'

        self.secret_id = config.get('secret_id')
        self.secret_key = config.get('secret_key')
        self.proxy = config.get('proxy')
        self.region = config.get('region')
        self.policy = config.get('policy')
        bucket = config.get('bucket')
        if bucket is not None:
            split_index = bucket.rfind('-')
            short_bucket_name = bucket[:split_index]
            appid = bucket[(split_index+1):]
            self.resource = "qcs::cos:{region}:uid/{appid}:prefix//{appid}/{short_bucket_name}/{allow_prefix}".format(
                region=config['region'],appid=appid,short_bucket_name=short_bucket_name,
                allow_prefix=config['allow_prefix']
            )

    @staticmethod
    def get_policy(scopes=[]):
        if not isinstance(scopes, list):
            return None
        policy = dict()
        policy['version'] = '2.0'
        statement = list()

        for scope in scopes:
            statement_element = dict()
            actions = list()
            resources = list()

            actions.append(scope.get_action())

            statement_element['action'] = actions

            statement_element['effect'] = 'allow'

            principal = dict()
            principal['qcs'] = list('*')
            statement_element['principal'] = principal

            resources.append(scope.get_resource())
            statement_element['resource'] = resources

            statement.append(statement_element)

        policy['statement'] = statement
        return policy

    def get_credential(self):
        try:
            import ssl
        except ImportError as e:
            raise e

        if self.policy is None:
            policy = {
                'version': '2.0',
                'statement': {
                    'action': self.allow_actions,
                    'effect': 'allow',
                    'principal': {'qcs': '*'},
                    'resource': self.resource
                }
            }
        else:
            policy = self.policy
        policy_encode = quote(json.dumps(policy))

        data = {
            'SecretId': self.secret_id,
            'Timestamp': int(time.time()),
            'Nonce': random.randint(100000, 200000),
            'Action': 'GetFederationToken',
            'Version': '2018-08-13',
            'DurationSeconds':self.duration,
            'Name': 'cos-sts-python',
            'Policy': policy_encode,
            'Region': 'ap-guangzhou'
        }
        data['Signature'] = self.__encrypt('POST', self.sts_url, data)

        try:
            response = requests.post(self.sts_scheme + self.sts_url, proxies=self.proxy, data=data)
            result_json = response.json()

            if isinstance(result_json['Response'], dict):
                result_json = result_json['Response']
       
            result_json['startTime'] = result_json['ExpiredTime'] - self.duration
            
            return self._backwardCompat(result_json)
        except requests.exceptions.HTTPError as e:
            raise e

    def __encrypt(self, method, url, key_values):
        source = Tools.flat_params(key_values)
        source = method + url + '?' + source
        try:
            key = bytes(self.secret_key) # Python 2.X
            source = bytes(source)
        except TypeError:
            key = bytes(self.secret_key, encoding='utf-8') # Python 3.X
            source = bytes(source, encoding='utf-8')
        sign = hmac.new(key, source, hashlib.sha1).digest()
        sign = base64.b64encode(sign).rstrip()
        return sign

    # v2接口的key首字母小写，v3改成大写，此处做了向下兼容
    def _backwardCompat(self, result_json):
        bc_json = dict()
        for k,v in result_json.items():
            if isinstance(v, dict):
                bc_json[k[0].lower() + k[1:]] = self._backwardCompat(v)
            elif k == 'Token':
                bc_json['sessionToken'] = v
            else:
                bc_json[k[0].lower() + k[1:]] = v
        
        return bc_json


class Tools(object):

    @staticmethod
    def _flat_key_values(a):
        return a[0] + '=' + str(a[1])

    @staticmethod
    def _link_key_values(a, b):
        return a + '&' + b

    @staticmethod
    def flat_params(key_values):
        key_values = sorted(key_values.items(), key=lambda d: d[0])
        return reduce(Tools._link_key_values, map(Tools._flat_key_values, key_values))


class Scope(object):
    action = None
    bucket = None
    region = None
    resource_prefix = None

    def __init__(self, action=None, bucket=None, region=None, resource_prefix=None):
        self.action = action
        self.bucket = bucket
        self.region = region
        self.resource_prefix = resource_prefix

    def set_bucket(self, bucket):
        self.bucket = bucket

    def set_region(self, region):
        self.region = region

    def set_action(self, action):
        self.action = action

    def set_resource_prefix(self, resource_prefix):
        self.resource_prefix = resource_prefix

    def get_action(self):
        return self.action

    def get_resource(self):
        split_index = self.bucket.rfind('-')
        bucket_name = str(self.bucket[:split_index]).strip()
        appid = str(self.bucket[(split_index + 1):]).strip()
        if not str(self.resource_prefix).startswith('/'):
            self.resource_prefix = '/' + self.resource_prefix
        resource = "qcs::cos:{region}:uid/{appid}:" \
                   "prefix//{appid}/{bucket_name}{prefix}".format(region=self.region,
                                                                  appid=appid,
                                                                  bucket_name=bucket_name,
                                                                  prefix=self.resource_prefix)
        return resource

    def get_dict(self):
        result = dict()
        result['action'] = self.action;
        result['bucket'] = self.bucket
        result['region'] = self.region
        result['prefix'] = self.resource_prefix
        return result

