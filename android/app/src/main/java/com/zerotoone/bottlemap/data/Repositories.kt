// Common Customer repository holder, available in both product flavors.
package com.zerotoone.bottlemap.data

object Repositories {
    val customer: CustomerRepository by lazy { CustomerRepository() }
}
