# Spackbot Documentation

Hi I'm spackbot! 👋  I can help you with [spack](https://github.com/spack/spack) pull requests in many ways!

- [Say hello](#say-hello)
- [Ask Spackbot for Help](#help)
- [Run Pipelines](#pipelines)
- [Style](#style)
- [Labels](#labels)
- [Maintainers](#maintainers)
- [Packages](#packages)
- [Issues](#issues)

## Quick Start
 
Here are some quick commands to get you started, and you can check out more detailed [developer guide](developer-guide/developer-guide) or [user guide](user-guide/user-guide). There are several different was you might want to interact with me, and other ways I will interact with you!

### Say hello

Want to give me a friendly hello? I always love a quick wave, so if you want to say hello:

```bash
@spackbot hello!
```

### Help

Oh no! I've you've forgotten a command, hopefully you can remember how to ask me for help! There are two ways:

```bash
@spackbot help
@spackbot commands
```

### Pipelines

Spack runs an additional pipeline on GitLab CI. If you have write access to the repository (meaning you opened the PR or are a maintainer) you can ask me to re-run the GitLab pipeline for you!

```bash
@spackbot run pipeline
@spackbot re-run pipeline
```

## Interactions

I'm a hard working robot, so I'll also be helping on the following things without you needing to ask!

### Style

If your style checks fail (meaning import order, linting, etc.) I'll give you a heads up, and give you a command to run to fix them automatically. If you have write access you can then ask me to fix the style for you.

### Labels

Don't you love GitHub labels? I do! Whenever you open a pull request, I'll take a peek at what changes you've made and add the appropriate labels. I'm just trying to help the maintainers out!

### Maintainers

Are you opening a pull request for a package? I'll help to find and ping maintainers for it! And if there aren't any, I'll start a discussion to figure out who might be able to do it.

And I just might have some other commands and jokes up my sleeve! Want to learn more? Browse the links on the left navigation, or
<a href="https://github.com/spack/spack-bot" target="_blank">ask me a question</a>. Thanks for stopping by! 😉

### Packages

It's often easier (and faster!) to review pull requests when they are opened for single packages.
Toward this aim, if Spackbot sees that you've opened a pull request that is changing multiple packages,
he will suggest to open a different pull request for each package.

### Issues

When you open an issue, it's important to triage and notify the people that can help as
quickly as possible. Spackbot helps here by looking for known package names in the title
of the issue, and then pinging maintainers that might know about the package. This means
that if you are opening an issue on a package, you should include the package name
in the title.
