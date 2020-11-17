require 'sinatra'
require 'octokit'
require 'dotenv/load' # Manages environment variables
require 'json'
require 'openssl'     # Verifies the webhook signature
require 'jwt'         # Authenticates a GitHub App
require 'time'        # Gets ISO 8601 representation of a Time object
require 'logger'      # Logs debug statements
require 'set'
require 'tmpdir'
require 'open3'


set :port, 3000
set :bind, '0.0.0.0'


class GHAapp < Sinatra::Application

  # Converts the newlines. Expects that the private key has been set as an
  # environment variable in PEM format.
  PRIVATE_KEY = OpenSSL::PKey::RSA.new(ENV['GITHUB_PRIVATE_KEY'].gsub('\n', "\n"))

  # Your registered app must have a secret set. The secret is used to verify
  # that webhooks are sent by GitHub.
  WEBHOOK_SECRET = ENV['GITHUB_WEBHOOK_SECRET']

  # The GitHub App's identifier (type integer) set when registering an app.
  APP_IDENTIFIER = ENV['GITHUB_APP_IDENTIFIER']

  # Turn on Sinatra's verbose logging during development
  configure :development do
    set :logging, Logger::DEBUG
  end


  # Executed before each request to the `/event_handler` route
  before '/event_handler' do
    get_payload_request(request)
    verify_webhook_signature
    authenticate_app
    # Authenticate the app installation in order to run API operations
    authenticate_installation(@payload)
  end


  post '/event_handler' do

    case request.env['HTTP_X_GITHUB_EVENT']
    when 'pull_request'
      # Action is 'opened' when PR is first opened,
      # and 'synchronize' when a new commit is added.
      # https://developer.github.com/webhooks/event-payloads/#pull_request
      if @payload['action'] === 'opened' || @payload['action'] === 'synchronize'
        label_pull_requests(@payload)
      end

      # Don't want to request maintainers for every single new commit,
      # only new PRs.
      if @payload['action'] === 'opened'
        add_reviewers(@payload)
      end
    end

    200 # success status
  end


  helpers do

    # Return an array of packages that were modified by a PR.
    # Ignore deleted packages, since we can no longer query
    # them for maintainers.
    def changed_packages(payload)
      repo = payload['repository']['full_name']
      number = payload['pull_request']['number']

      logger.debug("Looking for changed packages...")

      # See which files were modified
      # https://docs.github.com/en/free-pro-team@latest/rest/reference/pulls#list-pull-requests-files
      # https://octokit.github.io/octokit.rb/Octokit/Client/PullRequests.html#pull_request_files-instance_method
      files = @installation_client.pull_request_files(repo, number)

      packages = []
      files.each do |file|
        filename = file['filename']
        status = file['status']

        logger.debug("Filename: #{filename}")
        logger.debug("Status: #{status}")

        # Check if this is a package change.
        if filename =~ /^var\/spack\/repos\/builtin\/packages\/(\w[\w-]*)\/package.py$/
          package = $1
        else
          next
        end

        logger.debug("Package: #{package}")

        # Cannot query maintainers for a package that no longer exists
        if status === 'removed'
          next
        end

        packages.push(package)
      end

      return packages
    end

    # Return an array of packages with maintainers, an array of packages without
    # maintainers, and a set of maintainers. Ignore the author of the PR, as they
    # don't need to review their own PR.
    def find_maintainers(packages, payload)
      number = payload['pull_request']['number']
      author = payload['pull_request']['user']['login']
      clone_url = payload['repository']['clone_url']

      packages_with_maintainers = []
      packages_without_maintainers = []
      maintainers = Set.new

      logger.debug("Looking for maintainers...")

      Dir.mktmpdir('spack-') {|dir|
        # Clone appropriate PR branch
        system("git", "clone", "#{clone_url}", chdir: dir)
        system("git", "fetch", "origin", "pull/#{number}/head:PR#{number}", chdir: "#{dir}/spack")
        system("git", "checkout", "PR#{number}", chdir: "#{dir}/spack")

        # Add `spack` to PATH
        ENV['PATH'] = "#{dir}/spack/bin:#{ENV['PATH']}"

        packages.each do |package|
          logger.debug("Package: #{package}")

          # Query maintainers
          pkg_maintainers, status = Open3.capture2("spack", "maintainers", "#{package}")
          pkg_maintainers = Set.new(pkg_maintainers.split)

          logger.debug("Maintainers: #{pkg_maintainers}")

          if pkg_maintainers.empty?
            packages_without_maintainers.push(package)
            next
          end

          # No need to ask the author to review their own PR
          pkg_maintainers.delete(author)

          unless pkg_maintainers.empty?
            packages_with_maintainers.push(package)
            maintainers |= pkg_maintainers
          end
        end
      }

      return packages_with_maintainers, packages_without_maintainers, maintainers
    end

    # Add a comment on a PR to ping maintainers to review the PR.
    # If a package does not have any maintainers yet, request them.
    def add_reviewers(payload)
      repo = payload['repository']['full_name']
      number = payload['pull_request']['number']
      author = payload['pull_request']['user']['login']

      logger.debug("Looking for reviewers for PR ##{number}...")

      packages = changed_packages(payload)

      # Don't ask maintainers for review if hundreds of packages are modified,
      # it's probably just a license or Spack API change, not a package change.
      if packages.length() > 100
        return
      end

      packages_with_maintainers, packages_without_maintainers, maintainers = find_maintainers(packages, payload)

      unless maintainers.empty?
        # See which maintainers have permission to be reviewers
        # Need to be collaborators with 'write' or 'admin' permissions
        # https://developer.github.com/v3/repos/collaborators/
        # https://octokit.github.io/octokit.rb/Octokit/Client/Repositories.html
        reviewers = []
        non_reviewers = []
        maintainers.each do |user|
          logger.debug("User: #{user}")

          if @installation_client.collaborator?(repo, user)
            level = @installation_client.permission_level(repo, user)

            logger.debug("Permission level: #{level}")

            if level === 'write' || level === 'admin'
              reviewers.push(user)
            else
              non_reviewers.push(user)
            end
          else
            non_reviewers.push(user)
          end
        end

        # If they have permission, add them
        # https://developer.github.com/v3/pulls/review_requests/#create-a-review-request
        # https://octokit.github.io/octokit.rb/Octokit/Client/Reviews.html#request_pull_request_review-instance_method
        unless reviewers.empty?
          logger.debug("Requesting review from: #{reviewers}")

          # TODO: limit of 15 reviewers
          @installation_client.request_pull_request_review(repo, number, reviewers: reviewers)
        end

        # If not, give them permission and comment
        # https://octokit.github.io/octokit.rb/Octokit/Client/Issues.html#add_comment-instance_method
        unless non_reviewers.empty?
          logger.debug("Adding collaborators: #{non_reviewers}")

          non_reviewers.each do |user|
            @installation_client.add_collaborator(repo, user, permission: 'write')

          non_reviewers = non_reviewers.sort.join(' @')
          packages_with_maintainers = packages_with_maintainers.join("\n* ")
          comment = %Q(
  @#{non_reviewers} can you review this PR?

  This PR modifies the following package(s), for which you are listed as a maintainer:

  * #{packages_with_maintainers})
          @installation_client.add_comment(repo, number, comment)
        end
      end

      unless packages_without_maintainers.empty?
        # Ask for maintainers
        packages_without_maintainers = packages_without_maintainers.join("\n* ")
        comment = %Q(
Hi @#{author}! I noticed that the following package(s) don't yet have maintainers:

* #{packages_without_maintainers}

Are you interested in adopting any of these package(s)? If so, simply add the following to the package class:
```python
    maintainers = ['#{author}']
```
If not, could you contact the developers of this package and see if they are interested? Please don't add maintainers without their consent.

_You don't have to be a Spack expert or package developer in order to be a "maintainer", it just gives us a list of users willing to review PRs or debug issues relating to this package. A package can have multiple maintainers; just add a list of GitHub handles of anyone who wants to volunteer._)
        @installation_client.add_comment(repo, number, comment)
      end
    end

    # Add labels to PRs based on which files were modified.
    def label_pull_requests(payload)
      repo = payload['repository']['full_name']
      number = payload['pull_request']['number']

      logger.debug("Labeling PR ##{number}...")

      # See which files were modified
      # https://developer.github.com/v3/pulls/#list-pull-requests-files
      # https://octokit.github.io/octokit.rb/Octokit/Client/PullRequests.html#pull_request_files-instance_method
      files = @installation_client.pull_request_files(repo, number)

      labels = []
      files.each do |file|
        filename = file['filename']
        status = file['status']
        patch = file['patch']

        logger.debug("Filename: #{filename}")
        logger.debug("Status: #{status}")

        # Packages
        if filename =~ /^var\/spack\/repos\/builtin\/packages\/([^\/]+)\/package.py$/
          package = $1

          logger.debug("Package: #{package}")

          # Package name
          if package =~ /intel/
            labels.push('intel')
          end
          if package =~ /^python$/ || package =~ /^py-/
            labels.push('python')
          elsif package =~ /^r$/ || package =~ /^r-/
            labels.push('R')
          end

          # Package status
          if status === 'added'
            labels.push('new-package')
          elsif status === 'modified' || status == 'renamed'
            labels.push('update-package')
          end

          # Variables
          if patch =~ /[+-] +maintainers +=/
            labels.push('maintainers')
          end

          # Directives
          if patch =~ /\+ +version\(/
            labels.push('new-version')
          end
          if patch =~ /[+-] +conflicts\(/
            labels.push('conflicts')
          end
          if patch =~ /[+-] +depends_on\(/
            labels.push('dependencies')
          end
          if patch =~ /[+-] +extends\(/
            labels.push('extensions')
          end
          if patch =~ /[+-] +provides\(/
            labels.push('virtual-dependencies')
          end
          if patch =~ /[+-] +patch\(/
            labels.push('patch')
          end
          if patch =~ /\+ +variant\(/
            labels.push('new-variant')
          end
          if patch =~ /[+-] +resource\(/
            labels.push('resources')
          end

          # Functions
          if patch =~ /[+-] +def determine_spec_details\(/
            labels.push('external-packages')
          end
          if patch =~ /[+-] +def libs\(/
            labels.push('libraries')
          end
          if patch =~ /[+-] +def headers\(/
            labels.push('headers')
          end
          if patch =~ /[+-] +def test\(/
            labels.push('smoke-tests')
          end

        # Core Spack
        elsif filename =~ /^lib\/spack\/spack\/(architecture|operating_systems|platforms)/
          labels.push('architectures')
        elsif filename =~ /^lib\/spack\/spack\/binary_distribution/
          labels.push('binary-packages')
        elsif filename =~ /^lib\/spack\/spack\/build_environment/
          labels.push('build-environment')
        elsif filename =~ /^lib\/spack\/spack\/build_systems/
          labels.push('build-systems')
        elsif filename =~ /^lib\/spack\/spack\/cmd\/[^\/]+.py$/
          if status === 'added'
            labels.push('new-command')
          elsif status == 'modified' || status == 'renamed'
            labels.push('commands')
          end
        elsif filename =~ /^lib\/spack\/spack\/compiler/
          labels.push('compilers')
        elsif filename =~ /^lib\/spack\/spack\/directives/
          labels.push('directives')
        elsif filename =~ /^lib\/spack\/spack\/environment/
          labels.push('environments')
        elsif filename =~ /^lib\/spack\/spack\/(fetch|url|util\/url|util\/web)/
          labels.push('fetching')
        elsif filename =~ /^lib\/spack\/spack\/util\/lock/
          labels.push('locking')
        elsif filename =~ /^lib\/spack\/spack\/modules/
          labels.push('modules')
        elsif filename =~ /^lib\/spack\/spack\/stage/
          labels.push('stage')
        elsif filename =~ /^lib\/spack\/spack\/test/
          labels.push('tests')
        elsif filename =~ /^lib\/spack\/spack\/util/
          labels.push('utilities')
        elsif filename =~ /^lib\/spack\/spack\/version/
          labels.push('versions')

        # Documentation
        elsif filename =~ /^lib\/spack\/docs/
          labels.push('documentation')

        # GitHub
        elsif filename =~ /^\.travis/
          labels.push('travis')
        elsif filename =~ /^\.github\/actions/
          labels.push('actions')
        elsif filename =~ /^\.github\/workflows/
          labels.push('workflow')
        elsif filename =~ /^\.gitignore/
          labels.push('git')
        elsif filename =~ /^\.flake8/
          labels.push('flake8')
        elsif filename =~ /^LICENSE/
          labels.push('licenses')
        elsif filename =~ /^share\/spack\/gitlab/
          labels.push('gitlab')

        # Other
        elsif filename =~ /^etc\/spack\/defaults/
          labels.push('defaults')
        elsif filename =~ /^lib\/spack\/external/
          labels.push('vendored-dependencies')
        elsif filename =~ /^bin\/sbang$/
          labels.push('sbang')
        elsif filename =~ /[Dd]ockerfile$/ || filename =~ /^share\/spack\/docker/
          labels.push('docker')
        elsif filename =~ /^share\/spack\/.*sh/
          labels.push('shell-support')
        end
      end

      logger.debug("Adding the following labels: #{labels}")

      # https://developer.github.com/v3/issues/labels/#add-labels-to-an-issue
      # https://octokit.github.io/octokit.rb/Octokit/Client/Labels.html#add_labels_to_an_issue-instance_method
      @installation_client.add_labels_to_an_issue(repo, number, labels)
    end

    # Save the raw payload and convert the payload to JSON format
    def get_payload_request(request)
      # request.body is an IO or StringIO object
      # Rewind in case someone already read it
      request.body.rewind
      # The raw text of the body is required for webhook signature verification
      @payload_raw = request.body.read
      begin
        @payload = JSON.parse @payload_raw
      rescue => e
        fail "Invalid JSON (#{e}): #{@payload_raw}"
      end
    end

    # Instantiate an Octokit client authenticated as a GitHub App.
    # GitHub App authentication requires that you construct a
    # JWT (https://jwt.io/introduction/) signed with the app's private key,
    # so GitHub can be sure that it came from the app and was not altered by
    # a malicious third party.
    def authenticate_app
      payload = {
          # The time that this JWT was issued, _i.e._ now.
          iat: Time.now.to_i,

          # JWT expiration time (10 minute maximum)
          exp: Time.now.to_i + (10 * 60),

          # Your GitHub App's identifier number
          iss: APP_IDENTIFIER
      }

      # Cryptographically sign the JWT.
      jwt = JWT.encode(payload, PRIVATE_KEY, 'RS256')

      # Create the Octokit client, using the JWT as the auth token.
      @app_client ||= Octokit::Client.new(bearer_token: jwt)
    end

    # Instantiate an Octokit client, authenticated as an installation of a
    # GitHub App, to run API operations.
    def authenticate_installation(payload)
      @installation_id = payload['installation']['id']
      @installation_token = @app_client.create_app_installation_access_token(@installation_id)[:token]
      @installation_client = Octokit::Client.new(bearer_token: @installation_token)
    end

    # Check X-Hub-Signature to confirm that this webhook was generated by
    # GitHub, and not a malicious third party.
    #
    # GitHub uses the WEBHOOK_SECRET, registered to the GitHub App, to
    # create the hash signature sent in the `X-HUB-Signature` header of each
    # webhook. This code computes the expected hash signature and compares it to
    # the signature sent in the `X-HUB-Signature` header. If they don't match,
    # this request is an attack, and you should reject it. GitHub uses the HMAC
    # hexdigest to compute the signature. The `X-HUB-Signature` looks something
    # like this: "sha1=123456".
    # See https://developer.github.com/webhooks/securing/ for details.
    def verify_webhook_signature
      their_signature_header = request.env['HTTP_X_HUB_SIGNATURE'] || 'sha1='
      method, their_digest = their_signature_header.split('=')
      our_digest = OpenSSL::HMAC.hexdigest(method, WEBHOOK_SECRET, @payload_raw)
      halt 401 unless their_digest == our_digest

      # The X-GITHUB-EVENT header provides the name of the event.
      # The action value indicates the which action triggered the event.
      logger.debug("---- received event #{request.env['HTTP_X_GITHUB_EVENT']}")
      logger.debug("----    action #{@payload['action']}") unless @payload['action'].nil?
    end

  end

  # Finally some logic to let us run this server directly from the command line,
  # or with Rack. Don't worry too much about this code. But, for the curious:
  # $0 is the executed file
  # __FILE__ is the current file
  # If they are the same (that is, we are running this file directly), call the
  # Sinatra run method
  run! if __FILE__ == $0
end
