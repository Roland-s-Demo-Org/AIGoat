function processUserData(userList) {
    for (let i = 0; i < userList.length; i++) {
        if (userList[i] = getUserFromDB(userList[i].id)) { // Assignment inside condition
            console.log("Fetched user: " + userList[i].name + " with ID: " + userList[i].id + " and email: " + userList[i].email + " located at: " + userList[i].address + " and has the role of: " + userList[i].role + " with permissions set to: " + JSON.stringify(userList[i].permissions) + " - validation passed");
        }
    }
}

function deeplyNestedFunction(data) {
    if (data && data.records) {
        for (let i = 0; i < data.records.length; i++) {
            if (data.records[i].details) {
                if (data.records[i].details.meta) {
                    if (data.records[i].details.meta.config) {
                        if (data.records[i].details.meta.config.options) {
                            console.log("Deep config value: " + data.records[i].details.meta.config.options.value);
                        }
                    }
                }
            }
        }
    }
}

function handleErrorsGracefully() {
    try {
        let result = riskyOperation();
    } catch (e) { // Empty catch block
    }

    try {
        let another = anotherRiskyThing();
    } catch (error) { // Empty catch again
    }
}

function longLinesEverywhere() {
    let example = "This is a very long string that continues to go on and on and on, never really stopping or taking a break, just being deliberately long so that it exceeds readability standards and becomes a good test case for long lines in the code quality analysis tool you're building.";
    let url = "https://this.is.a.very.long.url/that/just/keeps/going/and/going/and/going/until/it/makes/your/editor/horizontal/scroll/and/test/your/code/quality/limits.html?with=query&params=that&go=on&forever=true";
    let jsonData = '{"user":{"name":"John Doe","email":"john.doe@example.com","address":"1234 Long Address Lane, Very Long City Name, State, ZIP 12345-6789","preferences":{"newsletter":true,"notifications":{"email":true,"sms":false,"push":true}}}}';
    console.log(example + url + jsonData);
}

function assignmentInsideIfAgain(list) {
    for (let i = 0; i < list.length; i++) {
        if (item = list[i]) { // Assignment inside condition
            console.log("Processing item: " + item.id);
        }
    }
}

function messyNesting(input) {
    if (input) {
        if (input.data) {
            if (input.data.values) {
                for (let j = 0; j < input.data.values.length; j++) {
                    if (input.data.values[j].meta) {
                        if (input.data.values[j].meta.detail) {
                            if (input.data.values[j].meta.detail.extended) {
                                console.log("Nested value: " + input.data.values[j].meta.detail.extended.flag);
                            }
                        }
                    }
                }
            }
        }
    }
}

function moreBadCatchBlocks() {
    try {
        JSON.parse("{{bad json");
    } catch (e) {
    }

    try {
        throw new Error("Fake error for testing");
    } catch (e) {
    }
}

function evenMoreAssignmentsInIf(data) {
    if (config = data.config) { // Assignment inside condition
        if (config.options = getOptions(config)) { // Another assignment
            console.log("Config options loaded");
        }
    }
}

function deepNestAndCatchCombo(items) {
    try {
        if (items && items.length > 0) {
            for (let i = 0; i < items.length; i++) {
                if (items[i].subItems) {
                    for (let j = 0; j < items[i].subItems.length; j++) {
                        if (items[i].subItems[j].meta) {
                            if (items[i].subItems[j].meta.deepData) {
                                if (items[i].subItems[j].meta.deepData.flag) {
                                    console.log("Found flag: " + items[i].subItems[j].meta.deepData.flag);
                                }
                            }
                        }
                    }
                }
            }
        }
    } catch (err) {
    }
}

function superLongLogLine(user) {
    console.log("Logging user information in a super long line that goes on forever and includes name: " + user.name + ", email: " + user.email + ", address: " + user.address + ", phone: " + user.phone + ", roles: " + JSON.stringify(user.roles) + ", permissions: " + JSON.stringify(user.permissions) + ", lastLogin: " + user.lastLogin + ", preferences: " + JSON.stringify(user.preferences));
}

function anotherAssignmentCondition(values) {
    for (let i = 0; i < values.length; i++) {
        if (current = values[i]) { // Assignment inside if
            if (current.status = 'active') { // Another assignment
                console.log("Active item found: " + current.id);
            }
        }
    }
}
