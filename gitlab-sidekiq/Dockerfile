FROM registry.gitlab.com/gitlab-org/build/cng/gitlab-sidekiq-ee:v16.11.10

# Enable sentry performance
# RUN sed -i 's/config\.traces_sample_rate = 0\.2 if/config.traces_sample_rate = 0.2 # if/' /srv/gitlab/lib/gitlab/error_tracking.rb

# Log yaml size on error
RUN sed -i '/raise DataTooLargeError, / s/raise DataTooLargeError, /raise DataTooLargeError, "The parsed YAML is too big (size: #{deep_size.instance_variable_get(:@size)} bytes)"/' /srv/gitlab/lib/gitlab/config/loader/yaml.rb
