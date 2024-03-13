FROM registry.gitlab.com/gitlab-org/build/cng/gitlab-webservice-ee:v16.9.2

RUN sed -i 's/subject.success? \&\& subject.has_warnings?/subject.success? # \&\& subject.has_warnings?/' /srv/gitlab/lib/gitlab/ci/status/success_warning.rb
