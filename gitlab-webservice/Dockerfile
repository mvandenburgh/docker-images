FROM registry.gitlab.com/gitlab-org/build/cng/gitlab-webservice-ee:v16.11.4

# Enable sentry performance
RUN sed -i 's/config\.traces_sample_rate = 0\.2 if/config.traces_sample_rate = 0.2 # if/' /srv/gitlab/lib/gitlab/error_tracking.rb
