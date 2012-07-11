from django.db import models
from django.core.exceptions import ValidationError


from mozdns.validation import validate_ip_type
from core.vlan.models import Vlan
from core.site.models import Site
from core.mixins import ObjectUrlMixin
from core.keyvalue.models import KeyValue

import ipaddr

class Network(models.Model, ObjectUrlMixin):
    id = models.AutoField(primary_key=True)
    vlan = models.ForeignKey(Vlan, null=True,
            blank=True, on_delete=models.SET_NULL)
    site = models.ForeignKey(Site, null=True,
            blank=True,on_delete=models.SET_NULL)

    # NETWORK/NETMASK FIELDS
    IP_TYPE_CHOICES = (('4', 'ipv4'), ('6', 'ipv6'))
    ip_type = models.CharField(max_length=1, choices=IP_TYPE_CHOICES,
                editable=True, validators=[validate_ip_type])
    ip_upper = models.BigIntegerField(null=False, blank=True)
    ip_lower = models.BigIntegerField(null=False, blank=True)
    # This field is here so ES can search this model easier.
    network_str = models.CharField(max_length=39, editable=True)
    prefixlen = models.PositiveIntegerField(null=False)

    network = None

    def details(self):
        return (
                ('Network', self.network_str),
                )

    class Meta:
        db_table = 'network'
        unique_together = ('ip_upper', 'ip_lower', 'prefixlen')

    def save(self, *args, **kwargs):
        self.update_network()
        super(Network, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.range_set.all().exists():
            raise ValidationError("Cannot delete this network because it has "
                "child ranges")
        super(Network, self).delete(*args, **kwargs)


    def clean(self):
        self.update_network()
        # Look at all ranges that claim to be in this subnet, are they actually
        # in the subnet?
        for range_ in self.range_set.all():
            if range_.start < int(self.network.network):
                raise ValidationError("Resizing this subnet to the requested "
                        "network prefix would orphan existing ranges.")
            if range_.end > int(self.network.broadcast):
                raise ValidationError("Resizing this subnet to the requested "
                        "network prefix would orphan existing ranges.")


    def update_network(self):
        """This function will look at the value of network_str to update other
        fields in the network object. This function will also set the 'network'
        attribute to either an ipaddr.IPv4Network or ipaddr.IPv6Network object.
        """
        if not isinstance(self.network_str, basestring):
            raise ValidationError("ERROR: No network str.")
        try:
            if self.ip_type == '4':
                self.network = ipaddr.IPv4Network(self.network_str)
            elif self.ip_type == '6':
                self.network = ipaddr.IPv6Network(self.network_str)
            else:
                raise ValidationError("Could not determine IP type of network"
                        " %s" % (self.network_str))
        except (ipaddr.AddressValueError, ipaddr.NetmaskValueError), e:
            raise ValidationError(str(e))
        # Update fields
        self.ip_upper = int(self.network) >> 64
        self.ip_lower = int(self.network) & (1 << 64) - 1  # Mask off
                                                     # the last sixty-four bits
        self.prefixlen = self.network.prefixlen

    def __str__(self):
        return self.network_str

    def __repr__(self):
        return "<Network {0}>".format(str(self))

class NetworkKeyValue(KeyValue):
    network = models.ForeignKey(Network, null=False)
    aux_attrs = (
        ('description', 'A description of the site'),
    )
    class Meta:
        db_table = 'network_key_value'
        unique_together = ('key', 'value')

    def description(self):
        return