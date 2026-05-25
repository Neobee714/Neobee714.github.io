# Step 1: Write nginx.conf without xyvora.me SSL block (cert not yet issued)
# neobee.top SSL still works; xyvora.me served over HTTP only for ACME challenge
new_nginx = """server {
    listen 80;
    server_name neobee.top www.neobee.top xyvora.me www.xyvora.me api.bookkeeping.neobee.top bookkeeping.neobee.top;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
        try_files $uri =404;
    }

    location / {
        return 301 https://xyvora.me$request_uri;
    }
}

# neobee.top -> redirect to xyvora.me (uses existing cert)
server {
    listen 443 ssl;
    server_name neobee.top www.neobee.top;

    ssl_certificate /etc/letsencrypt/live/neobee.top/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/neobee.top/privkey.pem;

    location / {
        return 301 https://xyvora.me$request_uri;
    }
}

# API
server {
    listen 443 ssl;
    server_name api.bookkeeping.neobee.top;
    client_max_body_size 60M;

    ssl_certificate /etc/letsencrypt/live/neobee.top/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/neobee.top/privkey.pem;

    location / {
        proxy_pass http://bookkeeping-backend:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
"""

with open('/root/neobee-stack/nginx.conf', 'w') as f:
    f.write(new_nginx)
print('nginx.conf updated (no xyvora.me SSL yet)')
