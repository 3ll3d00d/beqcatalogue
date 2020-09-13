#!/bin/sh

setup_git() {
  git config --global user.email "travis@travis-ci.org"
  git config --global user.name "Travis CI"
}

commit_files() {
  git checkout -b feature/travis-test
  git add -A
  git commit -m "Travis build: $TRAVIS_BUILD_NUMBER" -m "[ci skip]"
}

upload_files() {
  git remote add origin-pages https://${GH_TOKEN}@github.com/3ll3d00d/beqcatalogue.git > /dev/null 2>&1
  git push -set-upstream origin-pages HEAD
}

setup_git
commit_files
upload_files