import os
import json
import zipfile
import re
import sys
import base64
import glob
import ldap3

from urllib.parse import urlparse
from ldap3.utils import dn as dnutils

from setup_app import paths
from setup_app import static
from setup_app.utils import base
from setup_app.config import Config
from setup_app.utils.db_utils import dbUtils
from setup_app.utils.setup_utils import SetupUtils
from setup_app.utils.properties_utils import propertiesUtils
from setup_app.pylib.jproperties import Properties
from setup_app.installers.jetty import JettyInstaller
from setup_app.installers.base import BaseInstaller

class CollectProperties(SetupUtils, BaseInstaller):


    def __init__(self):
        pass

    def collect(self):
        print("Please wait while collectiong properties...")
        self.logIt("Previously installed instance. Collecting properties")
        salt_fn = os.path.join(Config.configFolder,'salt')
        if os.path.exists(salt_fn):
            salt_prop = base.read_properties_file(salt_fn)
            Config.encode_salt = salt_prop['encodeSalt']

        jans_prop = base.read_properties_file(Config.jans_properties_fn)
        Config.persistence_type = jans_prop['persistence.type']
        oxauth_ConfigurationEntryDN = jans_prop['jansAuth_ConfigurationEntryDN']
        jans_ConfigurationDN = 'ou=configuration,o=jans'

        if Config.persistence_type == 'couchbase':
            Config.mappingLocations = { group: 'couchbase' for group in Config.couchbaseBucketDict }
            default_storage = 'couchbase'

        if Config.persistence_type != 'ldap' and os.path.exists(Config.jansCouchebaseProperties):

            jans_cb_prop = base.read_properties_file(Config.jansCouchebaseProperties)

            Config.couchebaseClusterAdmin = jans_cb_prop['auth.userName']
            Config.encoded_cb_password = jans_cb_prop['auth.userPassword']
            Config.cb_password = self.unobscure(jans_cb_prop['auth.userPassword'])
            Config.couchbase_bucket_prefix = jans_cb_prop['bucket.default']

            Config.couchbase_hostname = jans_cb_prop['servers'].split(',')[0].strip()
            Config.encoded_couchbaseTrustStorePass = jans_cb_prop['ssl.trustStore.pin']
            Config.couchbaseTrustStorePass = self.unobscure(jans_cb_prop['ssl.trustStore.pin'])

        if Config.persistence_type != 'couchbase' and os.path.exists(Config.ox_ldap_properties):
            jans_ldap_prop = base.read_properties_file(Config.ox_ldap_properties)
            Config.ldap_binddn = jans_ldap_prop['bindDN']
            Config.ldapPass = self.unobscure(jans_ldap_prop['bindPassword'])
            Config.opendj_p12_pass = self.unobscure(jans_ldap_prop['ssl.trustStorePin'])
            Config.ldap_hostname, Config.ldaps_port = jans_ldap_prop['servers'].split(',')[0].split(':')


        if Config.persistence_type in ['hybrid']:
             jans_hybrid_properties = base.read_properties_file(jans_hybrid_properties_fn)
             Config.mappingLocations = {'default': jans_hybrid_properties['storage.default']}
             storages = [ storage.strip() for storage in jans_hybrid_properties['storages'].split(',') ]

             for ml, m in (('user', 'people'), ('cache', 'cache'), ('site', 'cache-refresh'), ('token', 'tokens')):
                 for storage in storages:
                     if m in jans_hybrid_properties.get('storage.{}.mapping'.format(storage),[]):
                         Config.mappingLocations[ml] = storage

        if not Config.get('couchbase_bucket_prefix'):
            Config.couchbase_bucket_prefix = 'jans'

        # It is time to bind database
        dbUtils.bind()

        result = dbUtils.search('ou=clients,o=jans', search_filter='(inum=1701.*)', search_scope=ldap3.SUBTREE)

        if result:
            Config.jans_radius_client_id = result['inum']
            Config.jans_ro_encoded_pw = result['jansClntSecret']
            Config.jans_ro_pw = self.unobscure(Config.jans_ro_encoded_pw)
    
            result = dbUtils.search('inum=5866-4202,ou=scripts,o=jans', search_scope=ldap3.BASE)
            if result:
                Config.enableRadiusScripts = result['jansEnabled']

            result = dbUtils.search('ou=clients,o=jans', search_filter='(inum=1402.*)', search_scope=ldap3.SUBTREE)
            if result:
                Config.oxtrust_requesting_party_client_id = result['inum']

        #admin_dn = None
        #result = dbUtils.search('o=jans', search_filter='(jansGrpTyp=jansManagerGroup)', search_scope=ldap3.SUBTREE)
        #if result:
        #    admin_dn = result['member'][0]


        #if admin_dn:
        #    for rd in dnutils.parse_dn(admin_dn):
        #        if rd[0] == 'inum':
        #            Config.admin_inum = str(rd[1])
        #            break

        oxConfiguration = dbUtils.search(jans_ConfigurationDN, search_scope=ldap3.BASE)
        if 'jansIpAddress' in oxConfiguration:
            Config.ip = oxConfiguration['jansIpAddress']

        oxCacheConfiguration = json.loads(oxConfiguration['jansCacheConf'])
        Config.cache_provider_type = str(oxCacheConfiguration['cacheProviderType'])

        Config.scim_rp_client_jks_pass = 'secret' # this is static

        # Other clients
        client_var_id_list = [
                    ('oxauth_client_id', '1001.'),
                    ('scim_rs_client_id', '1201.'),
                    ('scim_rp_client_id', '1202.'),
                    ]
        self.check_clients(client_var_id_list)

        result = dbUtils.search(
                        search_base='inum={},ou=clients,o=jans'.format(Config.oxauth_client_id),
                        search_scope=ldap3.BASE,
                        )
        Config.oxauthClient_encoded_pw = result['jansClntSecret']
        Config.oxauthClient_pw = self.unobscure(Config.oxauthClient_encoded_pw)

        dn_oxauth, oxAuthConfDynamic = dbUtils.get_oxAuthConfDynamic()

        o_issuer = urlparse(oxAuthConfDynamic['issuer'])
        Config.hostname = str(o_issuer.netloc)

        Config.oxauth_openidScopeBackwardCompatibility =  oxAuthConfDynamic.get('openidScopeBackwardCompatibility', False)

        if 'pairwiseCalculationSalt' in oxAuthConfDynamic:
            Config.pairwiseCalculationSalt =  oxAuthConfDynamic['pairwiseCalculationSalt']
        if 'legacyIdTokenClaims' in oxAuthConfDynamic:
            Config.oxauth_legacyIdTokenClaims = oxAuthConfDynamic['legacyIdTokenClaims']
        if 'pairwiseCalculationKey' in oxAuthConfDynamic:
            Config.pairwiseCalculationKey = oxAuthConfDynamic['pairwiseCalculationKey']
        if 'keyStoreFile' in oxAuthConfDynamic:
            Config.oxauth_openid_jks_fn = oxAuthConfDynamic['keyStoreFile']
        if 'keyStoreSecret' in oxAuthConfDynamic:
            Config.oxauth_openid_jks_pass = oxAuthConfDynamic['keyStoreSecret']


        ssl_subj = self.get_ssl_subject('/etc/certs/httpd.crt')
        Config.countryCode = ssl_subj['C']
        Config.state = ssl_subj['ST']
        Config.city = ssl_subj['L']
        Config.city = ssl_subj['L']
         
         #this is not good, but there is no way to retreive password from ldap
        if not Config.get('oxtrust_admin_password'):
            if Config.get('ldapPass'):
                Config.oxtrust_admin_password = Config.ldapPass
            elif Config.get('cb_password'):
                Config.oxtrust_admin_password = Config.cb_password

        if not Config.get('orgName'):
            Config.orgName = ssl_subj['O']

        #for service in jetty_services:
        #    setup_prop[jetty_services[service][0]] = os.path.exists('/opt/jans/jetty/{0}/webapps/{0}.war'.format(service))


        for s in ['jansScimEnabled']:
            setattr(Config, s, oxConfiguration.get(s, False))

        application_max_ram = 3072

        default_dir = '/etc/default'
        usedRatio = 0.001
        oxauth_max_heap_mem = 0

        jetty_services = JettyInstaller.jetty_app_configuration

        for service in jetty_services:
            service_default_fn = os.path.join(default_dir, service)
            if os.path.exists(service_default_fn):
                usedRatio += jetty_services[service]['memory']['ratio']
                if service == 'jans-auth':
                    service_prop = base.read_properties_file(service_default_fn)
                    m = re.search('-Xmx(\d*)m', service_prop['JAVA_OPTIONS'])
                    oxauth_max_heap_mem = int(m.groups()[0])

        if oxauth_max_heap_mem:
            ratioMultiplier = 1.0 + (1.0 - usedRatio)/usedRatio
            applicationMemory = oxauth_max_heap_mem / jetty_services['jans-auth']['memory']['jvm_heap_ration']
            allowedRatio = jetty_services['jans-auth']['memory']['ratio'] * ratioMultiplier
            application_max_ram = int(round(applicationMemory / allowedRatio))

        Config.os_type = base.os_type
        Config.os_version = base.os_version

        if not Config.get('ip'):
            Config.ip = self.detect_ip()

        Config.installScimServer = os.path.exists(os.path.join(Config.jetty_base, 'jans-scim/start.ini'))
        Config.installFido2 = os.path.exists(os.path.join(Config.jetty_base, 'jans-fido2/start.ini'))
        Config.installConfigApi = os.path.exists(os.path.join(Config.jansOptFolder, 'config-api'))

    def save(self):
        propertiesUtils.save_properties()
