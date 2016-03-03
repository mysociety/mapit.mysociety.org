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

  # NFS requires a host-only network
  # This also allows you to test via other devices (e.g. mobiles) on the same
  # network
  config.vm.network :private_network, ip: "10.11.12.13"

  # Django dev server
  config.vm.network "forwarded_port", guest: 8000, host: 8000
  # For accessing via Varnish
  config.vm.network "forwarded_port", guest: 8001, host: 81
  # For mailcatcher
  config.vm.network "forwarded_port", guest: 1080, host: 1080

  # Give the VM a bit more power to speed things up
  config.vm.provider "virtualbox" do |v|
    v.memory = 2048
    v.cpus = 2
  end

  # Provision the vagrant box
  config.vm.provision "shell", inline: <<-SHELL
    sudo apt-get update

    cd /vagrant/mapit.mysociety.org

    # Install the packages from conf/packages.ubuntu-trusty
    xargs sudo apt-get install -qq -y < conf/packages.ubuntu-trusty
    # Install some of the other things we need that are either just for dev
    # or can't come from the usual package manager
    # ruby-dev for mailcatcher
    # git for installing mapit from the repo directly
    sudo apt-get install -qq -y ruby-dev git

    # Create a postgresql user
    sudo -u postgres psql -c "CREATE USER mapit SUPERUSER CREATEDB PASSWORD 'mapit'"
    # Create a database
    sudo -u postgres psql -c "CREATE DATABASE mapit"
    # Install the POSTGIS extensions
    sudo -u postgres psql -c "CREATE EXTENSION postgis; CREATE EXTENSION postgis_topology;" -d mapit

    # Install mailcatcher to make dev email development easier
    sudo gem install mailcatcher

    # Run post-deploy actions script to create a virtualenv, install the
    # python packages we need, migrate the db and generate the sass etc
    conf/post_deploy_actions.bash
  SHELL

  # Start mailcatcher every time we start the VM
  config.vm.provision "shell", run: "always" do |s|
    s.inline = <<-SHELL
      mailcatcher --http-ip 0.0.0.0
      cd /vagrant
      source virtualenv-mapit_mysociety_org/bin/activate
    SHELL
  end
end
