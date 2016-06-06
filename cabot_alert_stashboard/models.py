from django.db import models
from django.conf import settings
from django.template import Context, Template

from cabot.cabotapp.alert import AlertPlugin

from os import environ as env
import requests
from requests_oauthlib import OAuth1

sb_alert_url = env['STASHBOARD_URI']
sb_create_services = env.get('STASHBOARD_CREATE_SERVICES') or False

sb_token = env['STASHBOARD_TOKEN']
sb_secret = env['STASHBOARD_SECRET']

sb_normal = env['STASHBOARD_NORMAL']
sb_warn = env['STASHBOARD_WARNING']
sb_error = env['STASHBOARD_ERROR']
sb_crit = env['STASHBOARD_CRITICAL']

#sb_template = "Service {{ service.name }} {% if service.overall_status == service.PASSING_STATUS %}is back to normal{% else %}reporting {{ service.overall_status }} status{% endif %}."

sb1_template = """Service {{ service.name }} {% if service.overall_status == service.PASSING_STATUS %}is back to normal{% else %} reporting {{ service.overall_status }} status{% endif %} {% if service.overall_status != service.PASSING_STATUS %}Checks failing: {% for check in service.all_failing_checks %}{% if check.check_category == 'Jenkins check' %}{% if check.last_result.error %}{{ check.name }} ({{ check.last_result.error|safe }}) {{jenkins_api}}job/{{ check.name }}/{{ check.last_result.job_number }}/console{% else %}{{ check.name }} {{jenkins_api}}/job/{{ check.name }}/{{check.last_result.job_number}}/console{% endif %}{% else %}{{ check.name }}{% if check.last_result.error %}({{ check.last_result.error|safe }}){% endif %}{% endif %}{% endfor %}{% endif %}{% if alert %}{% for alias in users %}@{{ alias }}{% endfor %}{% endif %}"""

class StashboardAlert(AlertPlugin):
    name = "Stashboard"
    author = "Oleksandr Nagorodniuk"

    def send_alert(self, service, users, duty_officers):

        # Stashboard handles repeat alerts, so we can skip them
        if service.overall_status == service.old_overall_status:
            return

        alert = True
        priority = sb_error

        if service.overall_status == service.WARNING_STATUS:
            priority = sb_warn
        elif service.overall_status == service.ERROR_STATUS:
            priority = sb_error
        elif service.overall_status == service.CRITICAL_STATUS:
            priority = sb_crit
        elif service.overall_status == service.PASSING_STATUS:
            priority = sb_normal
            if service.old_overall_status == service.CRITICAL_STATUS:
                # cancel the recurring crit
                pass
        else:
            # something weird happened
            alert = False

        if not alert:
            return
        # now let's send
        c = Context({
            'service': service,
            'host': settings.WWW_HTTP_HOST,
            'scheme': settings.WWW_SCHEME,
            'jenkins_api': settings.JENKINS_API,
            })
        message = Template(sb1_template).render(c)
        self._send_stashboard_alert(message, key=str(service.id), priority=priority, service=service)

    def _send_stashboard_alert(self, message, key, priority, service):
        # set up a session so we can do multiple requests easily
        s = requests.Session()
        s.auth = OAuth1(u'anonymous', u'anonymous',
                sb_token, sb_secret)

        resp = s.get('%s/services/%s' % (sb_alert_url, key))
        if resp.status_code == 404:
            if not sb_create_services:
                return
            if not service.url:
                service.url = service.name
            # first create the service with the Cabot ID as the name
            a = s.post('%s/services' % (sb_alert_url),
                    data={
                        'name': key,
                        'description': service.url,
                    },
                    headers={'Content-Type':None}
                )
            f = open( '/tmp/testfile1', 'w' )
            f.write( 'a.content = ' + a.content + '\n' )
            f.close()

            # now change the name to the name in Cabot
            a = s.post('%s/services/%s' % (sb_alert_url, key),
                    data={
                        'name': service.name,
                        'description': service.url,
                    },
                    headers={'Content-Type':None}
                )
            f = open( '/tmp/testfile', 'w' )
            f.write( 'b.content = ' + a.content + '\n' )
            f.close()

        payload = {
                'token':env['PUSHOVER_TOKEN'],
                'user': key,
                'status': priority,
                'message': message,
        }

        s.post(
                '%s/services/%s/events' % (sb_alert_url, key),
                data=payload,
                headers={'Content-Type':None}
            )
