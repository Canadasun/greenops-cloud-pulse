# Local IoT Hub stand-in (Role 2 – Marcelbriaud Wafotchoupe). The config and ACL are built into the image, owned by
# the broker user: Mosquitto 2.1 crashes when the ACL file belongs to a user unknown inside the container
# (e.g. a bind mount from a CI runner) and warns that it will refuse world-readable ACL files.
FROM eclipse-mosquitto:2
USER root
COPY --chown=1000:1000 --chmod=0644 mosquitto.conf /mosquitto/config/mosquitto.conf
COPY --chown=1000:1000 --chmod=0600 acl /mosquitto/config/acl
RUN chown -R 1000:1000 /mosquitto/data /mosquitto/log
USER 1000:1000
