# Bitbotcket

This is a script that provides a daily report on unanswered comments in Bitbucket PRs.

### Run Instructions
####Getting Bitbucket Credentials:
* Create a Bitbucket Bot User account (You could also use your own user account if comfortable).
* Obtain an [app password](https://support.atlassian.com/bitbucket-cloud/docs/app-passwords/) for the account, select account:read and pull_request:read permissions for your password.
* [Add the user](https://support.atlassian.com/bitbucket-cloud/docs/grant-access-to-a-workspace/) to your preferred workspace(s).
* The username and app password obtained form your `BITBUCKET_USERNAME` and `BITBUCKET_APP_PASSWORD` respectively.

####Getting Slack Credentials:
* Follow the instructions under `Add a bot user` on this [link](https://slack.com/help/articles/115005265703-Create-a-bot-for-your-workspace).
* Select the Bot Features & Functionality while creating your app.
* Review scopes and add the chat:write scope for your bot under Bot Token Scopes.
* Install to your workspace and obtain the OAuth token given. This forms your `SLACK_TOKEN`
* Make sure to add the installed bot to your channel of choice.

####Running:
* Create a .env file in the same directory as this README using .env.sample as a template.
* Set your
    * `BITBUCKET_USERNAME`: Obtained above
    * `BITBUCKET_APP_PASSWORD`: Obtained above
    * `SLACK_TOKEN`: Obtained above
    * `SLACK_CHANNEL`: Channel name where you want the bot to write updates to.
    * `WHEN_TO_RUN`: The time of day when you want the script to run in a HH:MM format. Note that the time used
  is local to the server where this script runs.
* Build and run with docker:
`docker build -t bitbotcket:latest . && docker run -it bitbotcket:latest`

### Note
* By default, the bitbucket bot user will target all repositories in all workspaces it has access to. You can limit the workspaces by setting
the env var `BITBUCKET_WORKSPACES` which is a comma separated list of Workspace IDs. The bot user must have access
to these workspaces.