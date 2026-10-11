# Application migration steps

# 1. Install Minikube cluster on Ubuntu

# 1. Create a VPC - custome subnet
10.10.10.0/24 - app
10.10.20.0/24 - nat

# 2. Create NAT Gateway nat-gateway

# 3. Two firewall rules 

allow-healthcheck-8080 (ipv4 ranges 35.191.0.0/16 and 130.211.0.0/22)
for google heatcheck
TCP - 8080

allow-proxy-only (ipv4 0.0.0.0/0 or ip address of LB)
TCP - 8080

# 4. Instance Template 
flask-template
allow -http traffic

Networking - add network as prod-vpc and subnet as app-subnet
external ip add as None.

Management- Startup script (flask app as a service)

# 5. Create a Managed Instance Group
mig-flask-app add instance temlate and then  

# 6. Create Global App LB
Add Network and proxy subnet
proxy-subnet - ipv4 range: 10.10.30.0/24

create a backend service: 
demo-health-check
http - 8080 on /health

# 7. Check the VM via ssh
curl localhost:8080

systemctl status flask.service

Take IP add of lb demo : 34.126.222.176:80


# 8. Cleanup activity

Delete LB Demo, then MIG, then templates, Delete Router, Delete NAT Gateway and finally Delete VPC
