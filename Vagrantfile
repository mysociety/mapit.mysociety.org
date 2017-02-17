# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure(2) do |config|
  # The most common configuration options are documented and commented below.
  # For a complete reference, please see the online documentation at
  # https://docs.vagrantup.com.

  # Every Vagrant development environment requires a box. You can search for
  # boxes at https://atlas.hashicorp.com/search.
  config.vm.box = "ubuntu/trusty64"

  # Enable NFS access to the disk
  config.vm.synced_folder "..", "/vagrant", :nfs => true

  # Speed up DNS lookups
  config.vm.provider "virtualbox" do |vb|
    vb.customize ["modifyvm", :id, "--natdnsproxy1", "off"]
    vb.customize ["modifyvm", :id, "--natdnshostresolver1", "off"]
  end

  # NFS requires a host-only network
  # This also allows you to test via other devices (e.g. mobiles) on the same
  # network
  config.vm.network :private_network, ip: "10.11.12.13"

  # Django dev server
  config.vm.network "forwarded_port", guest: 8000, host: 8000
  # For accessing via Varnish
  config.vm.network "forwarded_port", guest: 6081, host: 6081
  # For mailcatcher
  config.vm.network "forwarded_port", guest: 1080, host: 1080

  # Give the VM a bit more power to speed things up
  config.vm.provider "virtualbox" do |v|
    v.memory = 2048
    v.cpus = 2
  end

  # Provision the vagrant box
  config.vm.provision "shell", inline: <<-SHELL
    sudo echo 'deb http://debian.mysociety.org wheezy main' > /etc/apt/sources.list.d/mysociety.list
    wget --quiet -O - https://debian.mysociety.org/debian.mysociety.org.gpg.key | sudo apt-key add -

    sudo apt-get update

    cd /vagrant/mapit.mysociety.org

    # Install the packages from conf/packages.ubuntu-trusty
    xargs sudo apt-get install -qq -y < conf/packages.ubuntu-trusty
    # Install some of the other things we need that are just for dev
    # libsqlite3-dev and ruby-dev for mailcatcher, git for installing
    # mapit from the repo directly, and libvmod-redis
    sudo apt-get install -qq -y libsqlite3-dev ruby-dev git libvarnish-redis

    # Create a postgresql user
    sudo -u postgres psql -c "CREATE USER mapit SUPERUSER CREATEDB PASSWORD 'mapit'"
    # Create a database
    sudo -u postgres psql -c "CREATE DATABASE mapit"
    # Install the POSTGIS extensions
    sudo -u postgres psql -c "CREATE EXTENSION postgis; CREATE EXTENSION postgis_topology;" -d mapit

    # Install mailcatcher to make dev email development easier
    # https://github.com/sj26/mailcatcher/issues/277#issuecomment-262435023
    sudo gem install --no-rdoc --no-ri mime-types --version "< 3"
    sudo gem install --no-rdoc --no-ri mailcatcher --conservative

    # Copy the example config file into place to get things going
    cp conf/general.yml-example conf/general.yml

    # Run post-deploy actions script to create a virtualenv, install the
    # python packages we need, migrate the db and generate the sass etc
    conf/pre_deploy_actions.bash
    conf/post_deploy_actions.bash

    # Get the VCL from the varnish-api-key project
    wget --quiet -O - https://raw.githubusercontent.com/mysociety/varnish-apikey/master/vcl/varnish-apikey.vcl | sudo tee /etc/varnish/varnish-apikey.vcl > /dev/null

    # Install our own varnish config file
    sudo cp /vagrant/mapit.mysociety.org/conf/varnish.vcl-example /etc/varnish/default.vcl
    sudo service varnish restart
  SHELL

  # Start mailcatcher every time we start the VM
  config.vm.provision "shell", run: "always" do |s|
    s.inline = <<-SHELL
      mailcatcher --http-ip 0.0.0.0
    SHELL
  end
end
