#
# Cookbook Name:: persona-common
# Recipe:: app
#
# Copyright 2013, YOUR_COMPANY_NAME
#
# All rights reserved - Do Not Redistribute
#

group "browserid" do
  gid node[:persona][:browserid_uid]
end

user "browserid" do
  comment "Browserid Application User"
  uid node[:persona][:browserid_uid]
  gid node[:persona][:browserid_uid]
  home "/opt/browserid"
  supports :manage_home => true
end

directory "/var/browserid" do
  owner "root"
  group "browserid"
  mode 0755
end

directory "/var/browserid/log" do
  owner "browserid"
  group "browserid"
  mode 0755
end
