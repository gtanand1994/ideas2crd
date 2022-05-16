#!/usr/bin/env python
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import yaml
from string import Template

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

class Controller(BaseHTTPRequestHandler):
    def sync(self, parent, children):
        #Prechecks for parent

        app_details=dict()
        app_details['app_name']: str = parent['metadata']['name']
        app_details['env']: str = "prod"
        app_details['app_ns']: str = parent['metadata']['namespace']
        app_details['mesh']: str = "prod-alpha"
        app_details['app_port']: str = parent['spec']['app']['port']
        app_details['app_health_check']: str = parent['spec']['app']['health_check']
        app_details['cpu_threshold']: int = parent['spec']['app']['threshold']['cpu']
        app_details['mem_threshold']: int = parent['spec']['app']['threshold']['mem']
        app_details['app_endpoints']: list[str] = parent['spec']['app']['endpoints']['prod']
        app_details['canary_endpoints']: list[str] = parent['spec']['app']['endpoints']['canary']
        app_details['image_tag']: str = parent['spec']['app']['image']
        LOGGER.info("App details"+str(app_details))

        #Prechecks before creating resources


        # Compute status based on observed state.
        desired_status = {

        }

        childrens=dict()

        # Generate the desired child object(s).
        target_resources = []
        t,childrens = self.service_gen(app_details, childrens)
        target_resources += t
        t,childrens = self.scaled_object_gen(app_details, childrens)
        target_resources += t
        t,childrens = self.gw_vs_gen(app_details, childrens)
        target_resources += t
        t,childrens= self.argo_rollout_gen(app_details, childrens)
        target_resources += t
        t,childrens = self.argo_app_gen(app_details, childrens)
        target_resources += t
        LOGGER.info("Created Child resources"+str(childrens))

        return {"status": desired_status, "children": target_resources}

    def service_gen(self, app_details: dict, childrens: dict):
        f=open("/templates/roll_service.yaml",'r')
        s=f.read()
        f.close()
        temp_obj = Template(s)
        childrens["services"]=[]
        resource=[]
        for svc in ["stable","canary"]:
          resource.append(json.loads(json.dumps(yaml.safe_load(temp_obj.safe_substitute(J_APP_NAME=app_details['app_name']+"-"+svc,J_PROJECT_NAME=app_details['app_ns'],J_ENVIRONMENT=app_details['env'],J_APP_PORT=app_details['app_port'])))))
          childrens["services"].append(app_details['app_name']+"-"+svc)
        return resource,childrens

    def scaled_object_gen(self, app_details: dict, childrens: dict):
        f=open("/templates/roll_scaled-object.yaml",'r')
        s=f.read()
        f.close()
        temp_obj = Template(s)
        resource=[json.loads(json.dumps(yaml.safe_load(temp_obj.safe_substitute(J_APP_NAME=app_details['app_name'],J_PROJECT_NAME=app_details['app_ns'],J_CPU_PER=app_details['cpu_threshold'],J_MEM_PER=app_details['mem_threshold']))))]
        childrens["scaledobject"]=app_details['app_name']+"-so"
        return resource,childrens

    def gw_vs_gen(self, app_details: dict, childrens: dict):
        eps = dict()
        host,url="",""
        #LOGGER.info("endpoints:"+str(app_details['app_endpoints']+app_details['canary_endpoints']))
        for ep in list(app_details['app_endpoints'])+list(app_details['canary_endpoints']):
          #LOGGER.info("ep:"+str(ep))
          if len(ep.split('/',1)) == 1:
            host = ep
            url = ""
          else:
            host,url=ep.split('/',1)
          if host in list(eps.keys()):
            eps[host].append("/"+url)
          else:
            eps[host] = list("/"+url)

        #LOGGER.info("eps:"+str(eps))

        resource=[]
        childrens["gateways"]=[]
        childrens["virtualservices"]=[]
        f1=open("/templates/roll_gw.yaml",'r')
        s=f1.read()
        f1.close()
        temp_gw = Template(s)
        f2=open("/templates/roll_vs.yaml",'r')
        s=f2.read()
        f2.close()
        temp_vs = Template(s)
        f3=open("/templates/roll_vs-canary.yaml",'r')
        s=f3.read()
        f3.close()
        temp_vs_can = Template(s)
        for host in set([ a.split('/',1)[0] for a in list(app_details['app_endpoints'])]):
          if host.endswith(".com"):
            gw_name = app_details['app_name']+"-ext-gw"
            vs_name = app_details['app_name']+"-ext-vs"
          else:
            gw_name = app_details['app_name']+"-int-gw"
            vs_name = app_details['app_name']+"-int-vs"
          childrens["gateways"].append(gw_name)
          childrens["virtualservices"].append(vs_name)
          resource.append(json.loads(json.dumps(yaml.safe_load(temp_gw.safe_substitute(J_GW_NAME=gw_name,J_PROJECT_NAME=app_details['app_ns'],J_HOSTNAME=host)))))
          vs_def = json.loads(json.dumps(yaml.safe_load(temp_vs.safe_substitute(J_VS_NAME=vs_name,J_GW_NAME=gw_name,J_APP_NAME=app_details['app_name'],J_PROJECT_NAME=app_details['app_ns'],J_HOSTNAME=host,J_APP_PORT=app_details['app_port']))))
          for url in eps[host]:
            path={
                "uri": {
                  "prefix": "/"+url
                }
              }
            vs_def['spec']['http'][0]['match'].append(path)
          resource.append(vs_def)

        for host in set([ a.split('/',1)[0] for a in list(app_details['canary_endpoints'])]):
          if host.endswith(".com"):
            LOGGER.warning("Canary endpoint cannot be public")
          else:
            gw_name = app_details['app_name']+"-int-gw-canary"
            vs_name = app_details['app_name']+"-int-vs-canary"
          childrens["gateways"].append(gw_name)
          childrens["virtualservices"].append(vs_name)
          resource.append(json.loads(json.dumps(yaml.safe_load(temp_gw.safe_substitute(J_GW_NAME=gw_name,J_PROJECT_NAME=app_details['app_ns'],J_HOSTNAME=host)))))
          vs_def = json.loads(json.dumps(yaml.safe_load(temp_vs_can.safe_substitute(J_VS_NAME=vs_name,J_GW_NAME=gw_name,J_APP_NAME=app_details['app_name'],J_PROJECT_NAME=app_details['app_ns'],J_HOSTNAME=host,J_APP_PORT=app_details['app_port']))))
          for url in eps[host]:
            path={
                "uri": {
                  "prefix": "/"+url
                }
              }
            vs_def['spec']['http'][0]['match'].append(path)
          resource.append(vs_def)
        return resource,childrens


    def argo_rollout_gen(self, app_details: dict, childrens: dict):
        f=open("/templates/roll_deployment.yaml",'r')
        s=f.read()
        f.close()
        temp_obj = Template(s)
        childrens["rollout"]=app_details['app_name']
        resource=[json.loads(json.dumps(yaml.safe_load(temp_obj.safe_substitute(J_APP_NAME=app_details['app_name'],J_PROJECT_NAME=app_details['app_ns'],J_ENVIRONMENT=app_details['env'],J_MESH=app_details['mesh'],J_APP_PORT=app_details['app_port'],J_APP_HC=app_details['app_health_check'],J_IMAGE_TAG=app_details['image_tag']))))]
        resource[0]['spec']['strategy']['canary']['trafficRouting']['istio']['virtualServices']+=[ {"name":vs} for vs in childrens["virtualservices"] if not vs.endswith("canary")]
        return resource,childrens

    def argo_app_gen(self, app_details: dict, childrens: dict):
        f=open("/templates/argo_app.yaml",'r')
        s=f.read()
        f.close()
        temp_obj = Template(s)
        childrens["argoapp"]=app_details['app_name']
        resource=[json.loads(json.dumps(yaml.safe_load(temp_obj.safe_substitute(J_APP_NAME=app_details['app_name'],J_PROJECT_NAME=app_details['app_ns']))))]
        return resource,childrens

    def do_POST(self):
        # Serve the sync() function as a JSON webhook.
        observed = json.loads(self.rfile.read(int(self.headers.get("content-length"))))
        #post_data = self.rfile.read(int(self.headers.get("content-length"))) # <--- Gets the data itself
        #LOGGER.info("POST request,\nPath: %s\nHeaders:\n%s\n\nBody:\n%s\n",str(self.path), str(self.headers), post_data.decode('utf-8'))
        desired = self.sync(observed["parent"], observed["children"])

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(desired).encode())

HTTPServer(("", 80), Controller).serve_forever()
