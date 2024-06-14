#!/usr/bin/env python
import os
from aws_cdk import App, Environment
from site_stack import StaticSiteStack

app = App()
props = {
    "namespace": app.node.try_get_context("namespace"),
    "default_root_object": app.node.try_get_context("default_root_object"),
    "domain_name_www": app.node.try_get_context("domain_name_www"),
    "domain_name_root": app.node.try_get_context("domain_name_root"),
    "domain_name_id": app.node.try_get_context("domain_name_id"),
    "sub_domain_name": app.node.try_get_context("sub_domain_name"),
    "mon_email_address": app.node.try_get_context("mon_email_address"),
    "email_validation": app.node.try_get_context("email_validation"),
}

env = Environment(
    account=os.environ.get(
        "CDK_DEPLOY_ACCOUNT", os.environ.get("CDK_DEFAULT_ACCOUNT")
    ),
    region=os.environ.get(
        "CDK_DEPLOY_REGION", os.environ.get("CDK_DEFAULT_REGION")
    ),
)

StaticSite = StaticSiteStack(
    scope=app,
    construct_id=f"{props['namespace']}-stack",
    props=props,
    env=env,
    description="nwsl.me - Static Site using S3, CloudFront and Route53",
)

app.synth()
