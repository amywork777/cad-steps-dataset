"""
Onshape REST API access with HMAC authentication.
Python 3 port of onshape-public-apikey/python/apikey/onshape.py

Key changes from Python 2 original:
- urllib.parse instead of urllib/urlparse
- str/bytes handling for HMAC
- Removed .encode('utf-8') on already-str values
"""

from . import utils as api_utils

import os
import random
import string
import json
import hmac
import hashlib
import base64
import datetime
import requests
from urllib.parse import urlencode, urlparse, parse_qs

__all__ = ['Onshape']


class Onshape:
    """
    Provides access to the Onshape REST API.

    Attributes:
        - stack (str): Base URL
        - creds (str, default='./creds.json'): Credentials location
        - logging (bool, default=True): Turn logging on or off
    """

    def __init__(self, stack, creds='./creds.json', logging=True):
        if not os.path.isfile(creds):
            raise IOError(f'{creds} is not a file')

        with open(creds) as f:
            try:
                stacks = json.load(f)
                if stack in stacks:
                    self._url = stack
                    self._access_key = stacks[stack]['access_key']
                    self._secret_key = stacks[stack]['secret_key']
                    self._logging = logging
                else:
                    raise ValueError('specified stack not in file')
            except TypeError:
                raise ValueError(f'{creds} is not valid json')

        if self._logging:
            api_utils.log(f'onshape instance created: url = {self._url}, access key = {self._access_key}')

    def _make_nonce(self):
        """Generate a unique ID for the request, 25 chars in length."""
        chars = string.digits + string.ascii_letters
        nonce = ''.join(random.choice(chars) for _ in range(25))
        if self._logging:
            api_utils.log(f'nonce created: {nonce}')
        return nonce

    def _make_auth(self, method, date, nonce, path, query=None, ctype='application/json'):
        """Create the request signature to authenticate."""
        if query is None:
            query = {}

        query_str = urlencode(query)

        hmac_str = (method + '\n' + nonce + '\n' + date + '\n' + ctype +
                    '\n' + path + '\n' + query_str + '\n').lower().encode('utf-8')

        secret = self._secret_key.encode('utf-8') if isinstance(self._secret_key, str) else self._secret_key
        signature = base64.b64encode(hmac.new(secret, hmac_str, digestmod=hashlib.sha256).digest())
        auth = 'On ' + self._access_key + ':HmacSHA256:' + signature.decode('utf-8')

        if self._logging:
            api_utils.log({
                'query': query_str,
                'hmac_str': hmac_str,
                'signature': signature,
                'auth': auth
            })

        return auth

    def _make_headers(self, method, path, query=None, headers=None):
        """Creates a headers object to sign the request."""
        if query is None:
            query = {}
        if headers is None:
            headers = {}

        date = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
        nonce = self._make_nonce()
        ctype = headers.get('Content-Type', 'application/json')

        auth = self._make_auth(method, date, nonce, path, query=query, ctype=ctype)

        req_headers = {
            'Content-Type': 'application/json',
            'Date': date,
            'On-Nonce': nonce,
            'Authorization': auth,
            'User-Agent': 'Onshape Python Sample App',
            'Accept': 'application/json'
        }

        # add in user-defined headers
        for h in headers:
            req_headers[h] = headers[h]

        return req_headers

    def request(self, method, path, query=None, headers=None, body=None, base_url=None):
        """
        Issues a request to Onshape.

        Args:
            - method (str): HTTP method
            - path (str): Path e.g. /api/documents/:id
            - query (dict, default=None): Query params
            - headers (dict, default=None): Headers
            - body (dict, default=None): Body for POST request
            - base_url (str, default=None): Override host

        Returns:
            - requests.Response
        """
        if query is None:
            query = {}
        if headers is None:
            headers = {}
        if body is None:
            body = {}

        req_headers = self._make_headers(method, path, query, headers)
        if base_url is None:
            base_url = self._url
        url = base_url + path + '?' + urlencode(query)

        if self._logging:
            api_utils.log(body)
            api_utils.log(req_headers)
            api_utils.log(f'request url: {url}')

        # only parse as json string if we have to
        body = json.dumps(body) if isinstance(body, dict) else body

        res = requests.request(method, url, headers=req_headers, data=body,
                               allow_redirects=False, stream=True)

        if res.status_code == 307:
            location = urlparse(res.headers["Location"])
            querystring = parse_qs(location.query)

            if self._logging:
                api_utils.log(f'request redirected to: {location.geturl()}')

            new_query = {}
            new_base_url = location.scheme + '://' + location.netloc

            for key in querystring:
                new_query[key] = querystring[key][0]

            return self.request(method, location.path, query=new_query,
                                headers=headers, base_url=new_base_url)
        elif not 200 <= res.status_code <= 206:
            if self._logging:
                api_utils.log(f'request failed, details: {res.text}', level=1)
        else:
            if self._logging:
                api_utils.log(f'request succeeded, details: {res.text}')

        return res
