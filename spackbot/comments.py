# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import io
import random
import traceback
import spackbot.helpers as helpers


async def tell_joke(gh):
    """
    Tell a joke to ease the PR tension!
    """
    try:
        joke = await gh.getitem(
            "https://official-joke-api.appspot.com/jokes/programming/random"
        )
    except Exception:
        return "To be honest, I haven't heard any good jokes lately."

    joke = joke[0]
    return f"> {joke['setup']}\n *{joke['punchline']}*\n😄️"


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

    return f"""
I was able to run `spack style --fix` for you!
<details>
<summary><b>spack style --fix</b></summary>

```bash
{output}
```
</details>
Keep in mind that I cannot fix your flake8 or mypy errors, so if you have any you'll need to fix them and update the pull request.
If I was able to push to your branch, if you make further changes you will need to pull from your updated branch before pushing again.
"""


def format_error_message(msg, e_type, e_value, tb):
    """
    Given job failure details, format an error message to post.  The
    parameters e_type, e_value, and tb (for traceback) should be the same as
    returned by sys.exc_info().
    """
    buffer = io.StringIO()
    traceback.print_tb(tb, file=buffer)
    tb_contents = buffer.getvalue()
    buffer.close()

    return f"""
{msg}
<details>
<summary><b>Details</b></summary>

```bash
Error: {e_type}, {e_value}
Stack trace:
{tb_contents}
```
</details>
"""


commands_message = f"""
You can interact with me in many ways!

- `{helpers.botname} hello`: say hello and get a friendly response back!
- `{helpers.botname} help` or `{helpers.botname} commands`: see this message
- `{helpers.botname} run pipeline` or `{helpers.botname} re-run pipeline`: to request a new run of the GitLab CI pipeline
- `{helpers.botname} rebuild everything`: to run a pipeline rebuilding all specs from source.
- `{helpers.botname} fix style` if you have write and would like me to run `spack style --fix` for you.
- `{helpers.botname} maintainers` or `{helpers.botname} request review`: to look for and assign reviewers for the pull request.

I'll also help to label your pull request and assign reviewers!
If you need help or see there might be an issue with me, open an issue [here](https://github.com/spack/spack-bot/issues)
"""

style_message = f"""
It looks like you had an issue with style checks! I can help with that if you ask me!  Just say:

`{helpers.botname} fix style`

... and I'll try to fix style and push a commit to your fork with the fix.

Alternatively, you can run:

```bash
$ spack style --fix
```

And then update the pull request here.
"""

maintainer_request = """
It looks like you are opening an issue about a package, and we've found maintainers that might be able to help!

{maintainers}

"""


multiple_packages = """
Hey there! I noticed that you are adding or updating multiple packages:\n\n

{packages}

To get a speedier review for each, I'd like to suggest that you break this into multiple pull requests, with one per package.
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
$ spack blame {first_package_without_maintainer}
```
Thank you for your help! Please don't add maintainers without their consent.

_You don't have to be a Spack expert or package developer in order to be a "maintainer," it just gives us a list of users willing to review PRs or debug issues relating to this package. A package can have multiple maintainers; just add a list of GitHub handles of anyone who wants to volunteer._
"""
