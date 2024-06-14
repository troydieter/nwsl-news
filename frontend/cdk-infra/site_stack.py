from aws_cdk import Stack, RemovalPolicy, CfnOutput, Tags, Duration
from aws_cdk.aws_certificatemanager import Certificate, CertificateValidation
from aws_cdk.aws_cloudfront import Distribution, BehaviorOptions, PriceClass, ViewerProtocolPolicy, CachePolicy, \
    FunctionCode, FunctionAssociation, FunctionEventType, Function, ResponseHeadersPolicy, \
    ResponseSecurityHeadersBehavior, ResponseHeadersFrameOptions, \
    HeadersFrameOption, ResponseHeadersReferrerPolicy, ResponseHeadersContentTypeOptions, HeadersReferrerPolicy, \
    ResponseHeadersStrictTransportSecurity
from aws_cdk.aws_cloudfront_origins import S3Origin
from aws_cdk.aws_route53 import HostedZone, ARecord, RecordTarget, MxRecord, MxRecordValue, TxtRecord
from aws_cdk.aws_route53_targets import CloudFrontTarget
from aws_cdk.aws_s3 import Bucket, BlockPublicAccess, BucketEncryption
from aws_cdk.aws_s3_deployment import BucketDeployment, Source
from cdk_watchful import Watchful


class StaticSiteStack(Stack):
    def __init__(self, scope, construct_id, props, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        Tags.of(self).add("project", props["namespace"])
        Tags.of(self).add("website", props["namespace"] + ".me")
        www_domain_name = props["domain_name_www"]
        wildcard_domain_name = "*." + props["domain_name_root"]
        force_email_validation = props["email_validation"]
        site_namespace = props["namespace"]

        route53_zone = HostedZone.from_hosted_zone_attributes(self, "HostedZone",
            zone_name=props["domain_name_root"],
            hosted_zone_id=props["domain_name_id"]
        )
        cert = self.cert_creation(props, route53_zone, www_domain_name, wildcard_domain_name, force_email_validation)

        site_bucket = self.bucket_creation(www_domain_name, enforce_ssl=True, versioned=True)

        redirect_func = Function(self, "CFFunction", code=FunctionCode.from_file(file_path="cf-functions/redirect.js"),
                                 function_name="redirect_uri_" + site_namespace,
                                 comment="Redirect and rewrite index.html for " + site_namespace)

        sec_policy = self.sec_method

        site_distribution = self.static_site(cert, props, redirect_func, sec_policy, site_bucket, www_domain_name,
                                             site_namespace)

        self.site_contents(site_bucket, site_distribution)

        self.r53_records(props, route53_zone, site_distribution)

        wf = Watchful(self, "Watchful", alarm_email=props["mon_email_address"], dashboard=True,
                      dashboard_name=www_domain_name.replace('.', '') + "_dashboard")
        wf.watch_scope(self)

        # Add stack outputs
        CfnOutput(
            self,
            "SiteBucketName",
            value=site_bucket.bucket_name,
        )
        CfnOutput(
            self,
            "DistributionId",
            value=site_distribution.distribution_id,
        )
        CfnOutput(
            self,
            "DistributionDomainName",
            value=site_distribution.distribution_domain_name,
        )
        CfnOutput(
            self,
            "CertificateArn",
            value=cert.certificate_arn,
        )

    def bucket_creation(self, site_domain_name, enforce_ssl, versioned):
        site_bucket = Bucket(self, "Bucket",
                             block_public_access=BlockPublicAccess.BLOCK_ALL,
                             bucket_name=site_domain_name,
                             encryption=BucketEncryption.S3_MANAGED,
                             enforce_ssl=enforce_ssl,
                             versioned=versioned,
                             removal_policy=RemovalPolicy.DESTROY
                             )
        return site_bucket

    def site_contents(self, site_bucket, site_distribution):
        BucketDeployment(self, "DeployStaticSiteContents", sources=[Source.asset("../static")],
                         destination_bucket=site_bucket, distribution=site_distribution, distribution_paths=["/*"])

    def r53_records(self, props, route53_zone, site_distribution):
        ARecord(self, "wwwRecord", zone=route53_zone,
                target=RecordTarget.from_alias(CloudFrontTarget(site_distribution)), record_name="www")
        ARecord(self, "ApexRecord", zone=route53_zone,
                target=RecordTarget.from_alias(CloudFrontTarget(site_distribution)))
        # # Add MX records
        # MxRecord(self, "MailExchangeRecord1",
        #          zone=route53_zone,
        #          values=[MxRecordValue(host_name="mx1.improvmx.com.", priority=10)],
        #          comment="ImprovMX.com Record",
        #          delete_existing=True
        #          )
        #
        # MxRecord(self, "MailExchangeRecord2",
        #          zone=route53_zone,
        #          values=[MxRecordValue(host_name="mx2.improvmx.com.", priority=20)],
        #          comment="ImprovMX.com Record",
        #          delete_existing=True
        #          )
        # # Add SPF records
        # TxtRecord(self, "TxtRecord", zone=route53_zone,
        #           values=["v=spf1 include:spf.improvmx.com ~all"],
        #           comment="ImprovMX SPF TXT Record")

    def static_site(self, cert, props, redirect_func, sec_policy, site_bucket, site_domain_name, site_namespace):
        site_distribution = Distribution(self, "SiteDistribution",
                                         comment=site_namespace,
                                         price_class=PriceClass.PRICE_CLASS_100,
                                         default_root_object=props["default_root_object"],
                                         domain_names=[props["domain_name_root"], site_domain_name],
                                         certificate=cert,
                                         default_behavior=BehaviorOptions(origin=S3Origin(site_bucket),
                                                                          viewer_protocol_policy=ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                                                                          cache_policy=CachePolicy.CACHING_OPTIMIZED,
                                                                          function_associations=[FunctionAssociation(
                                                                              function=redirect_func,
                                                                              event_type=FunctionEventType.VIEWER_REQUEST)],
                                                                          response_headers_policy=sec_policy))
        return site_distribution

    @property
    def sec_method(self):
        sec_policy = ResponseHeadersPolicy(self, "SecPolicy",
                                           security_headers_behavior=ResponseSecurityHeadersBehavior(
                                               content_type_options=ResponseHeadersContentTypeOptions(
                                                   override=True),
                                               frame_options=ResponseHeadersFrameOptions(
                                                   frame_option=HeadersFrameOption.DENY, override=True),
                                               referrer_policy=ResponseHeadersReferrerPolicy(
                                                   referrer_policy=HeadersReferrerPolicy.NO_REFERRER,
                                                   override=True),
                                               strict_transport_security=ResponseHeadersStrictTransportSecurity(
                                                   access_control_max_age=Duration.days(30),
                                                   include_subdomains=True, override=True),
                                           ))
        return sec_policy

    # def r53_zone(self, props):
    #     r53_zone = HostedZone(self, "MainZone",
    #                           zone_name=props["domain_name_root"],
    #                           comment=props["namespace"]
    #                           )
    #     r53_zone.apply_removal_policy(RemovalPolicy.RETAIN)
    #     return r53_zone

    def cert_creation(self, props, route53_zone, site_domain_name, wildcard_domain_name, force_email_validation):
        if force_email_validation:
            validation_method = CertificateValidation.from_email()
        else:
            validation_method = CertificateValidation.from_dns(route53_zone)

        cert = Certificate(self, "SiteCertificate",
                           domain_name=props["domain_name_root"],
                           subject_alternative_names=[site_domain_name, wildcard_domain_name],
                           validation=validation_method
                           )
        return cert
