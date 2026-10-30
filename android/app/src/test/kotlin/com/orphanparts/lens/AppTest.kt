package com.orphanparts.lens

import com.orphanparts.lens.api.Readiness
import com.orphanparts.lens.ui.serviceLine
import org.junit.Assert.assertEquals
import org.junit.Test

class AppTest {
    @Test
    fun the_service_line_says_where_the_backend_stands() {
        assertEquals("No backend yet: pair the phone or type the address.", serviceLine("", null, null))
        assertEquals("192.168.1.20:8000 · checking…", serviceLine("http://192.168.1.20:8000", null, null))
        assertEquals("host · not reachable: refused", serviceLine("https://host", null, "not reachable: refused"))
        assertEquals(
            "host · recorded answers (nothing spent) · demo gated",
            serviceLine("https://host", Readiness("ok", "fixture (key failed)", true), null),
        )
        assertEquals(
            "host · live models · demo open",
            serviceLine("https://host", Readiness("ok", "live for the code, recorded otherwise", false), null),
        )
    }
}
