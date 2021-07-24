# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import random
import requests
import spackbot.helpers as helpers


def tell_joke():
    """
    Tell a joke to ease the PR tension!
    """
    response = requests.get(
        "https://official-joke-api.appspot.com/jokes/programming/random"
    )
    if response.status_code == 200:
        joke = response.json()[0]
        return "> %s\n *%s*\n😄️" % (joke["setup"], joke["punchline"])
    return "I'm a little tired now for a joke, but hey, you're funny looking! 😄️"


def say_hello():
    """
    Respond to saying hello.
    """
    messages = [
        "Hello!",
        "Hi! How are you?",
        "👋️",
        "Hola!",
        "Hey there!",
        "Howdy!",
        "こんにちは！",
    ]
    return random.choice(messages)


def get_style_message(output):
    """
    Given a terminal output, wrap in a message
    """
    # The output is limited to what GitHub can store in comments, 65,536 4-byte unicode
    # total rounded down -300 for text below
    if len(output) >= 64700:
        output = output[:64682] + "\n... truncated ..."

    return (
        """
I was able to run `spack style --fix` for you!
<details>
<summary><b>spack style --fix</b></summary>  
  
```bash
%s
```    
</details>
Keep in mind that I cannot fix your flake8 or mypy errors, so if you have any you'll need to fix them and update the pull request."""
        % output
    )


commands_message = """
You can interact with me in many ways! 

- `%s hello`: say hello and get a friendly response back!
- `%s help` or `%s commands`: see this message 
- `%s run pipeline` or `%s re-run pipeline`: to request a new run of the GitLab CI pipeline 
- `%s fix style` if you have write and would like me to run `spack style --fix` for you.
- `%s maintainers` or `%s request review`: to look for and assign reviewers for the pull request.

I'll also help to label your pull request and assign reviewers!
If you need help or see there might be an issue with me, open an issue [here](https://github.com/spack/spack-bot/issues)
""" % (
    helpers.botname,
    helpers.botname,
    helpers.botname,
    helpers.botname,
    helpers.botname,
    helpers.botname,
    helpers.botname,
    helpers.botname,
)

style_message = """
It looks like you had an issue with style checks! To fix this, you can run:

```bash
$ spack style --fix
```

And then update the pull request here.
"""

non_reviewers_comment = """\
  @{non_reviewers} can you review this PR?

  This PR modifies the following package(s), for which you are listed as a maintainer:

  * {packages_with_maintainers}
"""

no_maintainers_comment = """\
Hi @{author}! I noticed that the following package(s) don't yet have maintainers:

* {packages_without_maintainers}

Are you interested in adopting any of these package(s)? If so, simply add the following to the package class:
```python
    maintainers = ['{author}']
```
If not, could you contact the developers of this package and see if they are interested? You can quickly see who has worked on a package with `spack blame`:

```bash
$ spack blame var/spack/repos/builtin/packages/zlib/package.py
```
Thank you for your help! Please don't add maintainers without their consent.

_You don't have to be a Spack expert or package developer in order to be a "maintainer," it just gives us a list of users willing to review PRs or debug issues relating to this package. A package can have multiple maintainers; just add a list of GitHub handles of anyone who wants to volunteer._
"""
