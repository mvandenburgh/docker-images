FROM debian:stable-slim AS patch_builder
RUN apt-get update && apt-get install -y patch && rm -rf /var/lib/apt/lists/*

FROM registry.gitlab.com/gitlab-org/build/cng/gitlab-webservice-ee:v16.10.0

RUN cat /etc/os-release

COPY --from=patch_builder /usr/bin/patch /usr/bin/patch

COPY pipeline_serializer.patch /

# RUN sed -i 's/subject.success? \&\& subject.has_warnings?/subject.success? # \&\& subject.has_warnings?/' /srv/gitlab/lib/gitlab/ci/status/success_warning.rb
# RUN sed -i 's/\(preloader.preload_pipeline_warnings\)/#\1/' /srv/gitlab/lib/gitlab/ci/pipeline/preloader.rb
RUN patch -i /pipeline_serializer.patch /srv/gitlab/app/serializers/pipeline_serializer.rb
